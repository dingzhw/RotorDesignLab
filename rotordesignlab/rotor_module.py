"""Independent rotor documents; no aircraft mass, CG or installation required."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

import jsonschema
import numpy as np

from .cases import read_case, write_json, write_csv, read_rotor, numeric
from .hub_loads import BladeMass

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = read_case(ROOT / 'schemas/rotor-module.schema.json')
ASSETS = {'geometry.csv', 'polar.csv', 'polar.json'}


def validate(module):
    json.dumps(module, allow_nan=False)
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(module))
    if errors:
        raise ValueError('; '.join('/'.join(map(str, e.absolute_path)) + ': ' + e.message for e in errors))
    if type(module['schema_version']) is not int:
        raise ValueError('模块版本必须为整数。')
    rotor = module['rotor']
    for key in ('geometry_csv', 'polar_csv', 'polar_json'):
        if key in rotor and rotor[key] != {'geometry_csv': 'geometry.csv', 'polar_csv': 'polar.csv', 'polar_json': 'polar.json'}[key]:
            raise ValueError('模块数据表须使用包内固定文件名，不允许外部路径。')
    for key in ('rpm', 'collective_deg'):
        lo, hi = rotor['limits'][key]
        if lo >= hi:
            raise ValueError(key + '上下限须递增。')
    flap, mass = module['flapping'], module['blade_mass']
    length = rotor['radius_m'] - flap['hinge_offset_m']
    if length <= 0 or abs(flap['precone_deg']) > flap['max_flap_deg']:
        raise ValueError('铰偏置或预锥超出旋翼范围。')
    first, second = mass.get('first_mass_moment_kg_m'), mass.get('inertia_kg_m2')
    if first is not None and 'mass_kg' in mass and first > mass['mass_kg'] * length * (1 + 1e-12):
        raise ValueError('桨叶一阶质量矩超过质量乘铰外长度。')
    if first is not None and second is not None:
        if second > length * first * (1 + 1e-12):
            raise ValueError('铰外质量二阶矩超过长度乘一阶矩。')
        if 'mass_kg' in mass:
            BladeMass(mass['mass_kg'], first, second, length)
    hub = module['hub']
    if 'inertia_cg_kg_m2' in hub:
        inertia = np.array(hub['inertia_cg_kg_m2'])
        eigen = np.linalg.eigvalsh(inertia)
        if not np.allclose(inertia, inertia.T) or eigen[0] <= 0 or eigen[-1] > eigen[:2].sum() + 1e-10:
            raise ValueError('桨毂重心惯量须对称正定且满足主惯量三角关系。')


def asset_names(module):
    return [module['rotor'][key] for key in ('geometry_csv', 'polar_csv', 'polar_json') if key in module['rotor']]


def pack(module, assets):
    validate(module)
    if set(assets) != set(asset_names(module)):
        raise ValueError('模块数据表清单不一致。')
    manifest = dict(module=module, asset_hashes={k: sha256(v).hexdigest() for k, v in assets.items()})
    if sum(len(v) for v in assets.values()) + len(json.dumps(manifest).encode()) > 32*1024**2:
        raise ValueError('模块展开内容超过32 MB。')
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('module-manifest.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False))
        for name, data in assets.items():
            archive.writestr(name, data)
    return stream.getvalue()


def unpack(data):
    if len(data) > 32*1024**2:
        raise ValueError('模块包超过32 MB。')
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = archive.namelist()
            if len(names) > 4 or len(set(names)) != len(names) or sum(e.file_size for e in entries) > 32*1024**2:
                raise ValueError('模块包文件重复或超过限制。')
            manifest = json.loads(archive.read('module-manifest.json'))
            if set(manifest) != {'module', 'asset_hashes'}:
                raise ValueError('模块清单字段无效。')
            module = manifest['module']
            validate(module)
            expected = set(asset_names(module))
            if set(names) != expected | {'module-manifest.json'} or set(manifest['asset_hashes']) != expected:
                raise ValueError('模块包文件清单不一致。')
            assets = {k: archive.read(k) for k in expected}
            if any(sha256(v).hexdigest() != manifest['asset_hashes'][k] for k, v in assets.items()):
                raise ValueError('模块数据表哈希不一致。')
            return module, assets
    except (BadZipFile, KeyError, TypeError, UnicodeError, RuntimeError) as error:
        raise ValueError('无效旋翼模块包：' + str(error)) from error


def load(path):
    path = Path(path)
    if path.suffix == '.rdlr':
        return unpack(path.read_bytes())
    module = read_case(path)
    validate(module)
    return module, {name: (path.parent / name).read_bytes() for name in asset_names(module)}


def save(module, assets, path):
    """Exclusive creation: callers choose a new revision instead of overwriting."""
    data = pack(module, assets)
    with Path(path).open('xb') as stream:
        stream.write(data)


def extract(source, rotor_id, output):
    """Read a legacy aircraft/rdl; write a NEW module and migration evidence."""
    from .coordinates import selected_basis
    source, output = Path(source), Path(output)
    original = source.read_bytes()
    with TemporaryDirectory() as temp:
        if source.suffix == '.rdl':
            from .designs import unpack as read_design, materialize
            path = materialize(read_design(original), temp)
        else:
            path = source
        from .aircraft import read_aircraft
        aircraft = read_aircraft(path)
        matches = [r for r in aircraft['rotors'] if r['id'] == rotor_id]
        if not matches:
            raise ValueError('旧方案中没有指定旋翼。')
        old = matches[0]
        properties = SCHEMA['properties']['rotor']['properties']
        rotor = {k: deepcopy(v) for k, v in old.items() if k in properties}
        for key in ('cyclic_cos_deg', 'cyclic_sin_deg'):
            if key in old.get('flight', {}):
                rotor[key] = deepcopy(old['flight'][key])
        assets = {}
        for key, name in [('geometry_csv', 'geometry.csv'), ('polar_csv', 'polar.csv'), ('polar_json', 'polar.json')]:
            if key in rotor:
                assets[name] = (path.parent / rotor[key]).read_bytes()
                rotor[key] = name
        flap = deepcopy(old.get('flight', {}).get('flapping', dict(
            mode='fixed', hinge_offset_m=0., precone_deg=old.get('precone_deg', 0.), max_flap_deg=15.)))
        mass = deepcopy(old.get('blade_mass', {'provenance': '从旧旋翼字段原值提取；单片质量未提供，不由质量矩反推。'}))
        for key in ('inertia_kg_m2', 'first_mass_moment_kg_m'):
            if key in flap:
                mass[key] = flap.pop(key)
        module = dict(schema_version=1, kind='rotor_module', id=rotor_id, name=aircraft['name']+' / '+rotor_id,
                      axes='right_handed_z_thrust_x_zero', rotor=rotor, blade_mass=mass, flapping=flap,
                      hub=deepcopy(old.get('hub', {'provenance': '旧文件未提供桨毂独立质量/重心惯量。'})),
                      provenance=old.get('provenance', aircraft.get('provenance', '旧公开/用户方案原值，来源待核。')))
        validate(module)
        output.mkdir(parents=True, exist_ok=False)
        for name, data in assets.items():
            (output / name).write_bytes(data)
        write_json(output / 'module.json', module)
        save(module, assets, output / 'module.rdlr')
        basis = selected_basis(old)
        write_json(output / 'migration.json', dict(source_sha256=sha256(original).hexdigest(), rotor_id=rotor_id,
            rotor_to_body=basis.tolist(), original_position_m=old['position_m'],
            original_defaults=old['defaults'], original_flight=old.get('flight', {}),
            note='旧安装信息仅用于复算映射，不属于独立模块。局部来流/重力=基底转置乘原机体系向量。'))
        write_json(output / 'case.json', dict(schema_version=4, model='rotor_module', module_file='module.json',
            method='spatial', flapping_model='module', **old['defaults'], flow_rotor_m_s=[0.,0.,0.],
            gravity_rotor_m_s2=(basis.T @ np.array([0.,0.,9.80665])).tolist(),
            environment=dict(mode='custom', density_kg_m3=1.225,
                             speed_of_sound_m_s=old.get('speed_of_sound_m_s',340.3),
                             dynamic_viscosity_pa_s=old.get('dynamic_viscosity_pa_s',1.7894e-5))))
    return dict(status='converged', module=str(output/'module.rdlr'), source_unchanged=source.read_bytes()==original)


def convert_case(case, migration, reference):
    """Explicit migration of a matching isolated case, never a trim conversion."""
    from .coordinates import canonical_spatial_case, attitude_matrix
    from .isolated import COMMON_KEYS, SPATIAL_KEYS
    if set(case) - (COMMON_KEYS | SPATIAL_KEYS | {'axial_speed_m_s'}):
        raise ValueError('旧工况含未支持的字段，拒绝静默丢弃。')
    if case.get('model') not in ('spatial_rotor','aircraft_rotor') or case.get('rotor_id') != migration['rotor_id']:
        raise ValueError('仅转换同一旋翼的旧孤立工况；整机配平不是孤立旋翼工况。')
    result = deepcopy(reference)
    for key in ('rpm','collective_deg','radial_stations','azimuth_stations','cyclic_cos_deg','cyclic_sin_deg','target'):
        if key in case:
            result[key] = deepcopy(case[key])
    if 'environment' in case:
        result['environment'] = deepcopy(case['environment'])
        if 'altitude_m' in case:
            result['altitude_m'] = case['altitude_m']
    else:
        for key in ('density_kg_m3','speed_of_sound_m_s','dynamic_viscosity_pa_s'):
            if key in case:
                result['environment'][key] = case[key]
    # Overrides to module physical properties must not be silently discarded.
    if set(case) & {'precone_deg','tip_loss','inflow_model','polar_interpolation'}:
        raise ValueError('旧工况含旋翼模型覆盖项，请先显式另存对应模块再转换。')
    if case['model']=='spatial_rotor':
        resolved = canonical_spatial_case(case)
        basis = np.asarray(migration['rotor_to_body'])
        result['flow_rotor_m_s'] = (basis.T @ resolved['flow_body_m_s']).tolist()
        result['gravity_rotor_m_s2'] = (basis.T @ attitude_matrix(resolved.get('attitude_deg',[0.,0.])).T @ np.array([0.,0.,9.80665])).tolist()
        result['flapping_model'] = 'module' if case.get('flapping_model','fixed')=='aircraft' else 'fixed'
    else:
        result.update(method='axial',flapping_model='fixed',flow_rotor_m_s=[0.,0.,-case.get('axial_speed_m_s',0.)])
    return result


def run(case, base, output):
    from .coordinates import vector3
    from .environment import from_case, AIR_FIELDS
    from .isolated import evaluate, inverse, plot_elements
    allowed = {'schema_version','model','module_file','method','flapping_model','rpm','collective_deg','radial_stations',
               'azimuth_stations','flow_rotor_m_s','gravity_rotor_m_s2','cyclic_cos_deg','cyclic_sin_deg',
               'environment','altitude_m','target'}
    if set(case)-allowed:
        raise ValueError('模块工况未识别字段：'+str(sorted(set(case)-allowed)))
    if not isinstance(case.get('module_file'), str):
        raise ValueError('需要module_file。')
    module, assets = load(base / case['module_file'])
    for name, data in assets.items():
        (output / name).write_bytes(data)
    write_json(output / 'module.json', module)
    save(module, assets, output / 'module.rdlr')
    snapshot = dict(case, module_file='module.json')
    write_json(output / 'case.json', snapshot)
    write_json(output/'input-sha256.json', {name: sha256((output/name).read_bytes()).hexdigest() for name in ['module.json',*assets]})
    air = from_case(case)
    flow = vector3(case.get('flow_rotor_m_s'), '旋翼局部空气相对桨毂速度')
    gravity = vector3(case.get('gravity_rotor_m_s2'), '旋翼局部重力加速度')
    if np.linalg.norm(flow)>150 or flow[2]>1e-9:
        raise ValueError('当前支持来流≤150 m/s且正贯流（局部空气速度z≤0）。')
    spec = dict(module['rotor'], **{k:case.get(k) for k in ('rpm','collective_deg','radial_stations')},
                axial_speed_m_s=float(max(0.,-flow[2])), **{k:air[k] for k in AIR_FIELDS})
    rotor, _ = read_rotor(spec, output)
    for key in ('rpm','collective_deg'):
        if not module['rotor']['limits'][key][0] <= case[key] <= module['rotor']['limits'][key][1]:
            raise ValueError(key+'超出模块限位。')
    method = case.get('method', 'spatial')
    mode = case.get('flapping_model', 'module')
    if mode not in ('fixed','module') or method not in ('spatial','axial'):
        raise ValueError('方法选择spatial/axial，挥舞选择fixed/module。')
    config = deepcopy(module['flapping']) if mode=='module' else dict(mode='fixed',hinge_offset_m=0.,precone_deg=rotor.precone_deg,max_flap_deg=15.)
    if config['mode']=='hinged':
        missing = [k for k in ('inertia_kg_m2','first_mass_moment_kg_m') if k not in module['blade_mass']]
        missing += [k for k in ('spring_nm_rad','damper_nms_rad') if k not in config]
        if missing:
            raise ValueError('铰接挥舞缺少：'+', '.join(missing))
        config.update({k:module['blade_mass'][k] for k in ('inertia_kg_m2','first_mass_moment_kg_m')})
    cyclic = [numeric({'value':case.get(k,0.)},'value',-30,30) for k in ('cyclic_cos_deg','cyclic_sin_deg')]
    for key, value in zip(('cyclic_cos_deg','cyclic_sin_deg'), cyclic):
        if key in module['rotor'] and not module['rotor'][key][0] <= value <= module['rotor'][key][1]:
            raise ValueError(key+'超出模块限位。')
    selected = dict(rotation_sign=module['rotor']['rotation_sign'], limits=module['rotor']['limits'])
    target = None
    if method=='spatial':
        na = numeric({'value':case.get('azimuth_stations',36)},'value',12,720,integer=True)
        setup = (flow,np.eye(3),-flow,na,cyclic,config,gravity)
        if 'target' in case:
            rotor, answer, target = inverse(rotor,selected,setup,case['target'])
        else:
            answer = evaluate(rotor,selected,setup)
        model, state, loads, diagnostics = answer
        force, moment = loads['force'], loads['moment']
        summary = dict(thrust_n=float(force[2]), torque_nm=loads['torque'], power_w=loads['power'],
                       rpm=rotor.omega*30/np.pi, collective_deg=rotor.collective_deg,
                       flap_coning_deg=float(np.rad2deg(state[3])), flap_cos_deg=float(np.rad2deg(state[4])),
                       flap_sin_deg=float(np.rad2deg(state[5])))
        plot_elements(model,loads,output)
        kernel = model.kernel
        element_moment = np.cross(loads['position'], loads['element_force'])
        radial_thrust = rotor.blades * loads['element_force'][:,:,2].mean(axis=0)
        radial_torque = -selected['rotation_sign'] * rotor.blades * element_moment[:,:,2].mean(axis=0)
        write_csv(output/'radial_loads.csv',['radius_m','dr_m','thrust_n_per_m','torque_nm_per_m'],
                  zip(kernel.r,kernel.dr,radial_thrust/kernel.dr,radial_torque/kernel.dr))
        write_csv(output/'azimuth_loads.csv',['azimuth_deg','radius_m','ut','up','alpha_deg','cl','cd','fx_n','fy_n','fz_n'],
            ([float(np.rad2deg(psi)),float(radius),*[float(loads[k][i,j]) for k in ('ut','up','alpha_deg','cl','cd')],
              *loads['element_force'][i,j]] for i,psi in enumerate(model.kernel.psi) for j,radius in enumerate(model.kernel.r)))
    else:
        if np.linalg.norm(flow[:2])>1e-12 or any(cyclic) or config['mode']!='fixed':
            raise ValueError('轴流方法仅支持固定桨叶、纯轴向来流和零周期变距。')
        if not 0 <= config['precone_deg'] <= 15:
            raise ValueError('轴流性能模型预锥范围为0至15度。')
        from .rotor import solve
        from dataclasses import replace
        rotor = replace(rotor, precone_deg=config['precone_deg'])
        if 'target' in case:
            from .inverse import solve_target
            rotor, answer, target = solve_target(rotor,case['target'],selected['limits'])
        else:
            answer = solve(rotor)
        summary, columns, radial = answer
        write_csv(output/'radial_loads.csv',columns,radial)
        force = np.array([0.,0.,summary['thrust_n']])
        moment = np.array([0.,0.,-selected['rotation_sign']*summary['torque_nm']])
        diagnostics = {'flapping': 'fixed', 'inflow_model': rotor.inflow_model}
    margins = {k: v-summary[k] for k,v in selected['limits'].items() if k in ('power_w','torque_nm')}
    # A missing component rating leaves that design check unknown, not unlimited.
    if any(value < 0 for value in margins.values()):
        limits_status, feasible = 'exceeded', False
    elif len(margins) == 2:
        limits_status, feasible = 'satisfied', True
    else:
        limits_status, feasible = 'not_evaluated', None
    missing = [f'{group}/{key}' for group, keys in (
        ('blade_mass', ('mass_kg','first_mass_moment_kg_m','inertia_kg_m2')),
        ('hub', ('mass_kg','cg_rotor_m','inertia_cg_kg_m2')))
        for key in keys if key not in module[group]]
    warnings = ['独立旋翼整转平均气动载荷，力矩关于桨毂；未加入整机、安装或重心移轴。',
                '当前孤立稳态挥舞使用一阶/二阶质量矩；完整质量与桨毂属性在装配选择质量分账模型后参与整机惯性耦合。']
    from .model_scope import SPATIAL_SCOPE, MACH_SCOPE
    warnings += [MACH_SCOPE]
    if method == 'spatial':
        warnings += [SPATIAL_SCOPE, '三方向使用PP三状态入流；模块的环带入流/Prandtl选项只在轴流性能方法中使用。']
    solved = dict(snapshot, rpm=summary.get('rpm',case['rpm']),collective_deg=summary.get('collective_deg',case['collective_deg']))
    solved.pop('target',None)
    write_json(output/'solved-case.json',solved)
    write_csv(output/'rotor_loads.csv',['quantity','x','y','z'],[['force_rotor_n',*force],['moment_hub_rotor_nm',*moment]])
    (output/'report.md').write_text('# 独立旋翼计算\n\n'+ '\n\n'.join(warnings)+f"\n\n拉力 {summary['thrust_n']:.6g} N；轴功率 {summary['power_w']/1000:.6g} kW。\n",encoding='utf-8')
    return dict(summary=summary, force_rotor_n=force.tolist(), moment_hub_rotor_nm=moment.tolist(),
                target_solution=target, diagnostics=diagnostics, warnings=warnings,
                solver_status='converged', support_status='within_implemented_steady_domain',
                design_limits_status=limits_status, feasible=feasible, evidence_status='model_estimate',
                atmosphere=air, missing_mass_data=missing, parameter_usage={'blade_mass_kg':'stored_only','hub':'stored_only',
                'blade_mass_moments':'steady_flapping' if config['mode']=='hinged' else 'not_used_fixed'}), snapshot
