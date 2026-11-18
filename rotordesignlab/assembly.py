"""Versioned fixed rotor snapshots and their installations.

Module coordinates: right-handed z along thrust, x at zero azimuth. Installation
vectors are body X forward/Y right/Z down. The existing solver performs the
basis transform and CG moment shift; this adapter does not rotate loads twice.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math

import numpy as np

from . import rotor_module
from .coordinates import selected_basis

MODULE_FIELDS = set(rotor_module.SCHEMA['properties']['rotor']['properties'])
CYCLIC = {'cyclic_cos_deg', 'cyclic_sin_deg'}
MOMENTS = ('inertia_kg_m2', 'first_mass_moment_kg_m')
INSTALL_FIELDS = {'id', 'role', 'description', 'provenance', 'position_m', 'thrust_axis_body',
                  'defaults', 'transmission_efficiency', 'flight', 'speed_of_sound_m_s', 'dynamic_viscosity_pa_s'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def snapshot(module, assets):
    rotor_module.pack(module, assets)
    body = dict(module=deepcopy(module), assets={name: data.decode('utf-8-sig') for name, data in assets.items()})
    return dict(body, sha256=digest(body))


def module_data(instance):
    saved = instance['snapshot']
    return deepcopy(saved['module']), {name: value.encode('utf-8') for name, value in saved['assets'].items()}


def from_legacy(design):
    """Explicit new draft. The input and its original .rdl bytes are untouched."""
    if design.get('format_version') == 2:
        validate(design)
        return deepcopy(design)
    aircraft = design['aircraft']
    if aircraft.get('schema_version') != 2:
        raise ValueError('装配需要完整的一主旋翼加一尾桨机型；请从完整直升机模板新建。')
    result = deepcopy(design)
    instances = []
    for old in aircraft['rotors']:
        if 'flight' not in old:
            raise ValueError(old['id'] + '缺少安装零方位及挥舞资料，请先补齐；不推测旧方案定义。')
        rotor = {k: deepcopy(v) for k, v in old.items() if k in MODULE_FIELDS}
        rotor.update({k: deepcopy(old['flight'][k]) for k in CYCLIC if k in old['flight']})
        assets = {}
        for key, name in [('geometry_csv', 'geometry.csv'), ('polar_csv', 'polar.csv'), ('polar_json', 'polar.json')]:
            if key in rotor:
                assets[name] = design['assets'][rotor[key]].encode('utf-8')
                rotor[key] = name
        flap = deepcopy(old['flight']['flapping'])
        mass = deepcopy(old.get('blade_mass', {'provenance': '从原机型原值提取；单片质量未给定，不由质量矩反推。'}))
        for key in MOMENTS:
            if key in flap:
                mass[key] = flap.pop(key)
        module = dict(schema_version=1, kind='rotor_module', id=old['id'], name=aircraft['name']+' / '+old['id'],
                      axes='right_handed_z_thrust_x_zero', rotor=rotor, flapping=flap, blade_mass=mass,
                      hub=deepcopy(old.get('hub', {'provenance': '原机型未分列桨毂质量属性。'})), provenance=old.get('provenance', aircraft['provenance']))
        installation = {k: deepcopy(v) for k, v in old.items() if k not in MODULE_FIELDS | {'blade_mass', 'hub'}}
        ratio = installation.pop('rpm_ratio_to_main', None)
        installation['flight'] = {k: deepcopy(v) for k, v in old['flight'].items() if k not in CYCLIC | {'flapping'}}
        instances.append(dict(snapshot=snapshot(module, assets), installation=installation,
                              source={'kind': 'legacy_design', 'design_sha256': digest(design), 'rotor_id': old['id']},
                              drive=({'connection': 'powerplant', 'rpm_mode': 'main_ratio', 'ratio': ratio} if ratio is not None
                                     else {'connection': 'powerplant', 'rpm_mode': 'given'}),
                              controls='direct_blade_pitch_radians'))
    result['format_version'] = 2
    result['assembly'] = dict(schema_version=1, layout='single_main_tail', instances=instances,
                              mass_accounting='legacy_total_aircraft_no_automatic_rotor_addition')
    refresh(result)
    # Exact preservation, including existing asset names and missing optional fields.
    if result['aircraft'] != aircraft or result['assets'] != design['assets']:
        raise ValueError('转换后与原机型不一致，拒绝静默迁移。')
    validate(result)
    return result


def project(assembly, coupled=False):
    rotors, assets = [], {}
    instances = assembly['instances']
    main = next(i for i in instances if i['installation']['role'] == 'main')
    main_rpm = main['installation']['defaults']['rpm']
    for index, instance in enumerate(instances):
        saved = instance['snapshot']
        module = saved['module']
        rotor = deepcopy(instance['installation'])
        physical = deepcopy(module['rotor'])
        for key in CYCLIC:
            if key in physical:
                rotor['flight'][key] = physical.pop(key)
        for key in ('geometry_csv', 'polar_csv', 'polar_json'):
            if key in physical:
                old_name = physical[key]
                name = f'rotor-{index}-{key.replace("_", ".")}'
                assets[name] = saved['assets'][old_name]
                physical[key] = name
        rotor.update(physical)
        flap = deepcopy(module['flapping'])
        flap.update({key: module['blade_mass'][key] for key in MOMENTS if key in module['blade_mass']})
        rotor['flight']['flapping'] = flap
        if coupled:
            rotor['blade_mass'] = deepcopy(module['blade_mass'])
            rotor['hub'] = deepcopy(module['hub'])
        if instance['drive']['rpm_mode'] == 'main_ratio':
            rotor['defaults']['rpm'] = main_rpm * instance['drive']['ratio']
            rotor['rpm_ratio_to_main'] = instance['drive']['ratio']
        rotors.append(rotor)
    return rotors, assets


def refresh(design):
    from .mass_partition import enabled
    coupled = enabled(design['aircraft'])
    rotors, assets = project(design['assembly'], coupled)
    design['assembly']['mass_accounting'] = ('total_at_reference_flap_subtract_rotors' if coupled
                                            else 'legacy_total_aircraft_no_automatic_rotor_addition')
    design['aircraft']['rotors'] = rotors
    design['assets'] = assets


def validate(design):
    assembly = design.get('assembly')
    if (type(design.get('format_version')) is not int or design.get('format_version') != 2 or not isinstance(assembly, dict) or
            set(assembly) != {'schema_version', 'layout', 'instances', 'mass_accounting'} or
            type(assembly['schema_version']) is not int or assembly['schema_version'] != 1 or
            assembly['layout'] != 'single_main_tail' or
            assembly['mass_accounting'] not in ('legacy_total_aircraft_no_automatic_rotor_addition',
                                               'total_at_reference_flap_subtract_rotors')):
        raise ValueError('装配版本、布局或质量归属声明无效。')
    instances = assembly['instances']
    if not isinstance(instances, list) or len(instances) != 2:
        raise ValueError('当前装配仅支持一副主旋翼和一副尾桨。')
    roles, ids = [], []
    for instance in instances:
        if set(instance) != {'snapshot', 'installation', 'source', 'drive', 'controls'}:
            raise ValueError('安装实例字段不完整或含未知字段。')
        saved = instance['snapshot']
        if set(saved) != {'module', 'assets', 'sha256'} or saved['sha256'] != digest({k: saved[k] for k in ('module', 'assets')}):
            raise ValueError('旋翼模块快照哈希不一致。')
        module, assets = module_data(instance)
        rotor_module.pack(module, assets)
        install = instance['installation']
        if set(install) - INSTALL_FIELDS or not {'id', 'role', 'position_m', 'thrust_axis_body', 'defaults', 'flight', 'transmission_efficiency'} <= set(install):
            raise ValueError('安装实例只保存角色、位置、方向、参考转速与传动；不接受第二套旋翼本体参数。')
        if set(install['flight']) - {'x_reference_body', 'provenance'} or 'x_reference_body' not in install['flight']:
            raise ValueError('安装缺少零方位，或重复保存了旋翼挥舞参数。')
        roles.append(install['role'])
        ids.append(install['id'])
        defaults = install['defaults']
        for key in ('rpm', 'collective_deg', 'radial_stations'):
            value = defaults.get(key)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('安装参考值需要有限数值：' + key)
        if defaults['rpm'] <= 0:
            raise ValueError('安装参考转速必须大于零。')
        efficiency = install['transmission_efficiency']
        if type(efficiency) not in (int, float) or not math.isfinite(efficiency) or not 0 < efficiency <= 1:
            raise ValueError('旋翼传动效率须大于0且不超过1。')
        selected_basis(install)
        if not np.isclose(np.linalg.norm(install['thrust_axis_body']), 1., atol=1e-8, rtol=0):
            raise ValueError('安装正推力轴须为单位向量。')
        drive = instance['drive']
        if (set(drive) - {'connection', 'rpm_mode', 'ratio'} or drive.get('connection') != 'powerplant' or
                drive.get('rpm_mode') not in ('given', 'main_ratio')):
            raise ValueError('当前传动只支持共用动力接口、给定转速或尾桨相对主桨速比。')
        if drive['rpm_mode'] == 'main_ratio':
            ratio = drive.get('ratio')
            if install['role'] != 'tail' or type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio <= 0:
                raise ValueError('仅尾桨可采用正的主尾桨转速比。')
        elif 'ratio' in drive:
            raise ValueError('给定转速模式不接受隐藏的速比。')
        if instance['controls'] != 'direct_blade_pitch_radians':
            raise ValueError('当前操纵直接定义为桨叶变距角，不支持未实现的操纵映射。')
        if not isinstance(instance['source'], dict) or not instance['source'].get('kind'):
            raise ValueError('模块快照必须记录来源。')
    if sorted(roles) != ['main', 'tail'] or len(set(ids)) != 2:
        raise ValueError('需恰好一个主旋翼和一个尾桨，安装编号须不同。')
    from .mass_partition import enabled
    expected = ('total_at_reference_flap_subtract_rotors' if enabled(design['aircraft'])
                else 'legacy_total_aircraft_no_automatic_rotor_addition')
    if assembly['mass_accounting'] != expected:
        raise ValueError('装配质量归属声明与动力学模型不一致。')
    rotors, assets = project(assembly, enabled(design['aircraft']))
    if design['aircraft']['rotors'] != rotors or design['assets'] != assets:
        raise ValueError('整机求解输入与装配快照不一致；请从装配入口修改，不直接改生成的旋翼参数。')


def install(design, index, module, assets, source):
    """Explicit replacement; retain this instance's installation, never its case."""
    result = deepcopy(design)
    instance = result['assembly']['instances'][index]
    instance['snapshot'] = snapshot(module, assets)
    instance['source'] = deepcopy(source)
    refresh(result)
    validate(result)
    return result


def describe(design):
    rows = []
    for instance in design['assembly']['instances']:
        install = instance['installation']
        rotor = next(r for r in design['aircraft']['rotors'] if r['id'] == install['id'])
        rows.append({'安装编号': install['id'], '角色': '主旋翼' if install['role'] == 'main' else '尾桨',
                     '模块': instance['snapshot']['module']['name'], '快照SHA-256': instance['snapshot']['sha256'],
                     '桨毂位置 / m': install['position_m'], '正推力轴': install['thrust_axis_body'],
                     '零方位方向': install['flight']['x_reference_body'], '转速 / r/min': rotor['defaults']['rpm'],
                     '传动效率': install['transmission_efficiency']})
    return rows
