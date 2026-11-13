"""Aircraft data, isolated installed rotor analysis, and portable snapshots."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import jsonschema
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas' / 'aircraft.schema.json').read_text(encoding='utf-8'))
SCHEMA_V2 = json.loads((ROOT / 'schemas' / 'aircraft-v2.schema.json').read_text(encoding='utf-8'))
OPERATING_KEYS = ('rpm', 'collective_deg', 'radial_stations')
AERO_KEYS = ('precone_deg', 'speed_of_sound_m_s', 'inflow_model', 'tip_loss','dynamic_viscosity_pa_s')


def read_aircraft(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        aircraft = json.load(stream)
    try:
        # JSON permits non-finite constants in Python; reject them explicitly.
        json.dumps(aircraft, allow_nan=False)
        schema = SCHEMA_V2 if aircraft.get('schema_version') == 2 else SCHEMA
        errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(aircraft),
                        key=lambda item: str(list(item.absolute_path)))
        if errors:
            raise ValueError('; '.join(f'{"/".join(map(str, e.absolute_path))}: {e.message}' for e in errors))
    except (ValueError, jsonschema.ValidationError) as error:
        location = '/'.join(map(str, getattr(error, 'absolute_path', [])))
        raise ValueError(f'机型文件无效 {location}: {getattr(error, "message", str(error))}') from error
    if type(aircraft['schema_version']) is not int:
        raise ValueError('机型 schema_version 必须为整数。')
    mass = aircraft['mass_properties']
    if 'inertia_cg_kg_m2' in mass:
        inertia = np.asarray(mass['inertia_cg_kg_m2'], dtype=float)
        if not np.allclose(inertia, inertia.T, rtol=0, atol=1e-10):
            raise ValueError('重心惯量矩阵必须对称，非对角项填写惯量张量元素。')
        eigenvalues = np.linalg.eigvalsh(inertia)
        if eigenvalues[0] <= 0 or eigenvalues[-1] > eigenvalues[:2].sum() + 1e-10:
            raise ValueError('惯量矩阵必须正定，主惯量满足三角关系。')
    ids = [rotor['id'] for rotor in aircraft['rotors']]
    if len(ids) != len(set(ids)):
        raise ValueError('各旋翼 id 必须唯一。')
    for rotor in aircraft['rotors']:
        if type(rotor['rotation_sign']) is not int or type(rotor['blade_count']) is not int:
            raise ValueError('旋转符号和桨叶数必须为整数。')
        if not np.isclose(np.linalg.norm(rotor['thrust_axis_body']), 1, rtol=0, atol=1e-8):
            raise ValueError(f"{rotor['id']} 的推力轴必须是单位向量。")
        for key, absolute in (('rpm', (1, 30000)), ('collective_deg', (-20, 55))):
            low, high = rotor['limits'][key]
            if not absolute[0] <= low < high <= absolute[1]:
                raise ValueError(f"{rotor['id']} 的 {key} 限制区间无效。")
            if not low <= rotor['defaults'][key] <= high:
                raise ValueError(f"{rotor['id']} 的默认 {key} 超出机型限制。")
    if aircraft['schema_version'] == 2:
        if sorted(rotor['role'] for rotor in aircraft['rotors']) != ['main', 'tail']:
            raise ValueError('版本 2 悬停预算需要一个 main 和一个 tail 旋翼。')
        missing = [r['id'] + '/transmission_efficiency' for r in aircraft['rotors']
                   if 'transmission_efficiency' not in r]
        if missing:
            raise ValueError('悬停预算缺少参数：' + ', '.join(missing))
        plant = aircraft['powerplant']
        altitude = np.asarray(plant['altitude_m'])
        if np.any(np.diff(altitude) <= 0):
            raise ValueError('动力高度节点必须严格递增。')
        if any(len(plant[key]) != len(altitude) for key in ('continuous_power_w', 'short_time_power_w')):
            raise ValueError('动力曲线各列长度必须一致。')
        if np.any(np.asarray(plant['short_time_power_w']) < plant['continuous_power_w']):
            raise ValueError('短时功率不得低于连续功率。')
    return aircraft


def require_analysis(aircraft, analysis):
    """Capability gate; future analyses must never silently reuse a budget."""
    if analysis not in ('hover_budget', 'trim'):
        raise ValueError(f'整机分析 {analysis!r} 尚未实现；当前支持 hover_budget / trim。')
    if aircraft['schema_version'] != 2:
        raise ValueError('整机悬停预算需要机型版本 2；版本 1 继续用于孤立旋翼。')
    if analysis == 'trim':
        from .airframe import validate_trim_inputs
        validate_trim_inputs(aircraft)


def snapshot_aircraft(aircraft, source_dir, output):
    """Copy referenced inputs with stable local names and record their hashes."""
    from .cases import write_json
    snapshot = deepcopy(aircraft)
    hashes = {}
    for index, rotor in enumerate(snapshot['rotors']):
        polar_key = 'polar_json' if 'polar_json' in rotor else 'polar_csv'
        for key, suffix in (('geometry_csv', 'geometry'), (polar_key, 'polar')):
            source = Path(source_dir) / rotor[key]
            extension = 'json' if key == 'polar_json' else 'csv'
            name = f'rotor-{index}-{suffix}.{extension}'
            shutil.copyfile(source, output / name)
            rotor[key] = name
            hashes[name] = hashlib.sha256((output / name).read_bytes()).hexdigest()
    write_json(output / 'aircraft.json', snapshot)
    hashes['aircraft.json'] = hashlib.sha256((output / 'aircraft.json').read_bytes()).hexdigest()
    write_json(output / 'input-sha256.json', hashes)
    return snapshot


def prepare(case, base, output):
    from .cases import read_rotor
    allowed = {'schema_version', 'model', 'aircraft_json', 'rotor_id', 'density_kg_m3',
               'axial_speed_m_s', 'target', *OPERATING_KEYS, *AERO_KEYS}
    unknown = set(case) - allowed
    if unknown:
        raise ValueError(f'工况中未识别的字段：{sorted(unknown)}')
    if not isinstance(case.get('aircraft_json'), str) or not isinstance(case.get('rotor_id'), str):
        raise ValueError('请指定 aircraft_json 和 rotor_id。')
    source = (base / case['aircraft_json']).resolve()
    aircraft = read_aircraft(source)
    matches = [rotor for rotor in aircraft['rotors'] if rotor['id'] == case['rotor_id']]
    if not matches:
        raise ValueError(f"机型中没有旋翼 {case['rotor_id']}。")
    selected = matches[0]
    operating = dict(selected['defaults'])
    operating.update({key: case[key] for key in OPERATING_KEYS if key in case})
    for key in ('rpm', 'collective_deg'):
        value = operating[key]
        if type(value) not in (int, float) or not selected['limits'][key][0] <= value <= selected['limits'][key][1]:
            raise ValueError(f'{key} 超出所选机型的限制。')
    copied = snapshot_aircraft(aircraft, source.parent, output)
    selected_copy = next(rotor for rotor in copied['rotors'] if rotor['id'] == selected['id'])
    resolved = {key: selected_copy[key] for key in ('blade_count', 'radius_m', 'pitch_reference_r_over_R',
                                              'geometry_csv', 'polar_csv', 'polar_json', *AERO_KEYS) if key in selected_copy}
    resolved.update({key: case[key] for key in AERO_KEYS if key in case})
    resolved.update(operating, density_kg_m3=case.get('density_kg_m3', 1.225),
                    axial_speed_m_s=case.get('axial_speed_m_s', 0.0))
    model, _ = read_rotor(resolved, output)
    saved_case = dict(case, aircraft_json='aircraft.json', **operating)
    saved_case.setdefault('density_kg_m3', 1.225)
    saved_case.setdefault('axial_speed_m_s', 0.0)
    return model, aircraft, selected, saved_case


def installed_loads(aircraft, selected, summary):
    axis = np.asarray(selected['thrust_axis_body'], dtype=float)
    force = summary['thrust_n'] * axis
    arm = np.asarray(selected['position_m']) - np.asarray(aircraft['mass_properties']['cg_m'])
    reaction = -selected['rotation_sign'] * summary['torque_nm'] * axis
    moments = np.cross(arm, force) + reaction
    margins = {key: maximum - summary[key] for key, maximum in selected['limits'].items()
               if key in ('power_w', 'torque_nm')}
    return dict(aircraft_id=aircraft['id'], rotor_id=selected['id'],
                force_body_n=force.tolist(), moment_cg_body_nm=moments.tolist(),
                margins=margins, within_supplied_limits=all(value >= 0 for value in margins.values()),
                scope='isolated rotor loads at aircraft CG; whole-aircraft equilibrium not solved')
