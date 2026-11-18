"""Three designs, one fixed flight task, one steady trim model; no ranking."""
from copy import deepcopy
from hashlib import sha256
from math import isfinite, pi
from pathlib import Path
from time import perf_counter

import numpy as np
from . import __version__
from .aircraft import read_aircraft, snapshot_aircraft
from .cases import read_case, run_case, write_csv, write_json, table, numeric
from .hover import apply_design
from .power_accounting import POWER_TERMS
from .environment import from_case

DESIGN_KEYS = {'main_radius_m', 'main_rpm', 'tail_radius_m', 'tail_arm_m', 'cg_x_m'}
RULES = {'preserve_chord': '保持实际弦长与扭转', 'preserve_solidity': '保持实度与扭转（弦长随半径同比缩放）'}
CONTROL_LABELS = {'main_collective_deg': '主桨总距', 'main_cos_deg': '主桨cos周期变距',
                  'main_sin_deg': '主桨sin周期变距', 'tail_collective_deg': '尾桨总距'}
NOTICE = ('同一飞行质量、速度、高度、空气环境及维持时间的稳态方案比较；不自动评价最优方案。'
          '几何变化不自动更新质量矩/惯量，尺寸方案尚需结构与重量复核。'
          '全部结果为低阶模型估算；接近的差值应结合输入不确定性判断。开环排序仍受R19限制。')


def validate(spec, case):
    if set(spec) != {'schema_version', 'kind', 'case_json', 'variants'} or type(spec['schema_version']) is not int or spec['schema_version'] != 1:
        raise ValueError('同任务比较需要版本1、kind、case_json、variants。')
    if spec['kind'] != 'helicopter_design_comparison':
        raise ValueError('同任务比较类型错误。')
    common = {'schema_version', 'model', 'analysis', 'aircraft_json', 'speed_m_s', 'climb_m_s',
              'altitude_m', 'requested_duration_s', 'environment', 'radial_stations', 'azimuth_stations'}
    if not isinstance(case, dict) or set(case)-common or case.get('model') != 'helicopter' or case.get('analysis') != 'trim':
        raise ValueError('同任务比较需六分量配平工况；质量、重心、尺寸覆盖和续接初值不得放在共同工况中。')
    items = spec['variants']
    if not isinstance(items, list) or len(items) != 3:
        raise ValueError('本入口需要恰好三个候选方案。')
    names = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {'name', 'overrides', 'geometry_rule', 'provenance'}:
            raise ValueError('每方案需要名称、设计覆盖项、几何规则、来源说明。')
        if not isinstance(item['name'], str) or not item['name'].strip() or len(item['name']) > 80:
            raise ValueError('方案名称需为1–80字。')
        if not isinstance(item['provenance'], str) or not item['provenance'].strip():
            raise ValueError('请填写每个候选的来源或估算说明。')
        if item['geometry_rule'] not in RULES or not isinstance(item['overrides'], dict):
            raise ValueError('请明确半径变化的几何规则和设计覆盖项。')
        if set(item['overrides'])-DESIGN_KEYS:
            raise ValueError('同任务比较不允许改变任务条件；支持的设计变量为 '+', '.join(sorted(DESIGN_KEYS)))
        names.append(item['name'].strip())
    if len(set(names)) != 3:
        raise ValueError('三个方案名称不得重复。')


def prepare_candidate(aircraft, base, folder, item):
    changes = item['overrides']
    if any(type(v) not in (int, float) or not isfinite(v) for v in changes.values()):
        raise ValueError('候选设计参数必须为有限数值。')
    candidate = snapshot_aircraft(aircraft, base, folder)
    radii = {r['role']: r['radius_m'] for r in candidate['rotors']}
    # Existing A2 structural-override guard remains authoritative: do not invent
    # a new inertia after changing size/CG. An unchanged value is not an edit.
    effective = dict(changes)
    for rotor in candidate['rotors']:
        key = rotor['role']+'_radius_m'
        if effective.get(key) == rotor['radius_m']:
            effective.pop(key)
    if effective.get('cg_x_m') == candidate['mass_properties']['cg_m'][0]:
        effective.pop('cg_x_m')
    if 'cg_x_m' in effective:
        candidate['mass_properties']['cg_m'][0] = numeric(effective, 'cg_x_m', -100, 100)
    apply_design(candidate, effective)
    for rotor in candidate['rotors']:
        ratio = rotor['radius_m']/radii[rotor['role']]
        if ratio != 1 and item['geometry_rule'] == 'preserve_solidity':
            path = folder/rotor['geometry_csv']
            geometry = table(path, ('r_over_R', 'chord_m', 'twist_deg'))
            geometry[:, 1] *= ratio
            write_csv(path, ['r_over_R', 'chord_m', 'twist_deg'], geometry.tolist())
        rotor['provenance'] = rotor.get('provenance', '未填写')+'；本次候选：'+item['provenance']
    write_json(folder/'aircraft.json', candidate)
    files = [folder/'aircraft.json']+[folder/r[k] for r in candidate['rotors']
                                     for k in ('geometry_csv', 'polar_csv', 'polar_json') if k in r]
    write_json(folder/'input-sha256.json', {p.name: sha256(p.read_bytes()).hexdigest() for p in files})
    return candidate


def design_parameters(aircraft, folder):
    values = {'飞行质量_kg': aircraft['mass_properties']['mass_kg'],
              '重心X_m': aircraft['mass_properties']['cg_m'][0]}
    for rotor in aircraft['rotors']:
        name = '主桨' if rotor['role'] == 'main' else '尾桨'
        radius = rotor['radius_m']
        geometry = table(folder/rotor['geometry_csv'], ('r_over_R', 'chord_m', 'twist_deg'))
        # Planform solidity B*integral(c dr)/(pi R²), including the actual root cutout.
        solidity = rotor['blade_count']*np.trapezoid(geometry[:, 1], geometry[:, 0])/(pi*radius)
        values.update({name+'半径_m': radius, name+'转速_rpm': rotor['defaults']['rpm'],
                       name+'实度': float(solidity), name+'传动效率': rotor['transmission_efficiency']})
    tail = next(r for r in aircraft['rotors'] if r['role'] == 'tail')
    values['尾桨安装X_m'] = tail['position_m'][0]
    values['尾桨纵向力臂_m'] = aircraft['mass_properties']['cg_m'][0]-tail['position_m'][0]
    return values


def comparison_row(name, answer):
    state = {'converged': '已收敛', 'failed': '失败', 'within_implemented_steady_domain': '在当前支持范围',
             'within_supplied_limits': '满足给定限制', 'exceeded': '超限', 'not_evaluated': '未评估',
             'not_established': '未确定', 'outside_implemented_domain': '超出支持范围', 'not_converged': '未收敛'}
    row = {'方案': name}
    for key, title in [('solver_status', '求解'), ('support_status', '支持范围'), ('design_limits_status', '设计限制')]:
        value = answer.get(key, 'not_established')
        row[title] = state.get(value, value)
    row['验证依据'] = '模型估算'
    row['失败原因'] = answer.get('error', '')
    for key, title in POWER_TERMS.items():
        row[title+'_kW'] = answer.get('summary', {}).get(key, None)
        if row[title+'_kW'] is not None:
            row[title+'_kW'] /= 1000
    summary = answer.get('summary', {})
    for key, title in [('main_collective_deg', '主桨总距_deg'), ('main_cos_deg', '主桨cos周期变距_deg'),
                       ('main_sin_deg', '主桨sin周期变距_deg'), ('tail_collective_deg', '尾桨总距_deg'),
                       ('roll_deg', '滚转角_deg'), ('pitch_deg', '俯仰角_deg'),
                       ('main_thrust_n', '主桨推力_N'), ('tail_thrust_n', '尾桨推力_N'),
                       ('main_torque_nm', '主桨扭矩_Nm'), ('tail_torque_nm', '尾桨扭矩_Nm')]:
        row[title] = summary.get(key)
    ledger = answer.get('power_accounting', {})
    for component in ledger.get('components', []):
        title = '主桨' if component['role'] == 'main' else '尾桨'
        row[title+'传动损失_kW'] = component['loss_w']/1000
    row['所用可用功率_kW'] = ledger.get('selected_available_w', 0)/1000 if ledger else None
    row['额定口径'] = ('短时' if ledger['rating'] == 'short_time' else '连续') if ledger else '未评估'
    for key, title in CONTROL_LABELS.items():
        margins = answer.get('control_margins_deg', {}).get(key, {})
        row[title+'到下限_deg'] = margins.get('to_lower')
        row[title+'到上限_deg'] = margins.get('to_upper')
    return row


def run_comparison(spec, base, output):
    started = perf_counter()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('输出目录已有文件，请指定新的空目录。')
    with (output/'run.lock').open('x'):
        pass
    saved = deepcopy(spec)
    result = dict(schema_version=1, solver_version=__version__, model='helicopter_design_comparison',
                  status='failed', summary={}, candidates=[], warnings=[NOTICE], evidence_status='model_estimate')
    try:
        case_path = Path(base)/spec['case_json']
        case = read_case(case_path)
        validate(spec, case)
        source = case_path.parent/case['aircraft_json']
        aircraft = snapshot_aircraft(read_aircraft(source), source.parent, output)
        case = dict(case, aircraft_json='aircraft.json')
        saved['case_json'] = 'input-case.json'
        write_json(output/'input-case.json', case)
        result['common_task'] = {k: v for k, v in case.items() if k != 'aircraft_json'}
        result['common_mass_kg'] = aircraft['mass_properties']['mass_kg']
        rows = []
        for index, item in enumerate(spec['variants']):
            directory = output/f'candidate-{index+1}'
            inputs = directory/'inputs'
            inputs.mkdir(parents=True)
            write_json(directory/'design-change.json', item)
            entry = dict(name=item['name'], directory=directory.name, change=deepcopy(item),
                         geometry_rule=RULES[item['geometry_rule']], mass_inertia_update='未自动更新；仅作气动/配平设计比较')
            try:
                candidate = prepare_candidate(aircraft, output, inputs, item)
                entry['parameters'] = design_parameters(candidate, inputs)
                entry['sources'] = dict(aircraft=aircraft.get('provenance', '未填写'),
                                        mass_properties=candidate['mass_properties'].get('provenance', '未填写'),
                                        rotors={r['role']: r.get('provenance', '未填写') for r in candidate['rotors']},
                                        powerplant=candidate['powerplant'].get('provenance', '未填写'))
                child = dict(case, aircraft_json='inputs/aircraft.json')
                answer = run_case(child, directory, directory/'run')
                if answer['status'] == 'converged':
                    area = pi*next(r['radius_m'] for r in candidate['rotors'] if r['role'] == 'main')**2
                    entry['parameters']['主桨盘载_N_m2'] = answer['summary']['main_thrust_n']/area
                    for role, title in [('main', '主桨'), ('tail', '尾桨')]:
                        entry['parameters'][title+'局部最大Mach'] = answer['components'][role]['diagnostics']['mach_max']
                        rotor = next(r for r in candidate['rotors'] if r['role'] == role)
                        entry['parameters'][title+'旋转桨尖Mach'] = rotor['defaults']['rpm']*pi/30*rotor['radius_m']/from_case(case)['speed_of_sound_m_s']
            except (ValueError, OSError, KeyError, TypeError) as error:
                answer = dict(status='failed', solver_status='failed', support_status='not_established',
                              design_limits_status='not_evaluated', evidence_status='model_estimate', error=str(error))
                write_json(directory/'failure.json', answer)
            entry['result'] = answer
            result['candidates'].append(entry)
            row = comparison_row(item['name'], answer)
            row.update(entry.get('parameters', {}))
            row.update({'几何规则': entry['geometry_rule'], '质量惯量': entry['mass_inertia_update'], '候选来源': item['provenance']})
            rows.append(row)
        headers = list(dict.fromkeys(k for row in rows for k in row))
        write_csv(output/'design-comparison.csv', headers, [[r.get(k) for k in headers] for r in rows])
        failed = sum(c['result']['status'] != 'converged' for c in result['candidates'])
        result['status'] = 'converged' if failed == 0 else 'partial' if failed < 3 else 'failed'
        result['summary'] = dict(total=3, converged=3-failed, failed=failed,
                                 limit_violations=sum(c['result']['status'] == 'converged' and not c['result'].get('feasible', False)
                                                      for c in result['candidates']))
        if failed:
            result['error'] = f'{failed}个候选未获得有效配平；保留失败原因，不作为低功率方案。'
        from .design_comparison_report import render
        render(result, rows, output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result.update(status='failed', error=str(error))
    finally:
        result['elapsed_s'] = perf_counter()-started
        try:
            try:
                write_json(output/'batch.json', saved)
            except (ValueError, TypeError):
                result.update(status='failed', error='比较输入含不可保存的非有限值，请修正候选参数。')
            write_json(output/'result.json', result)
        finally:
            (output/'run.lock').unlink()
    return result
