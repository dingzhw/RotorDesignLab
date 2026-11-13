"""Two-equation hover load/power budget, explicitly not six-axis trim."""
from dataclasses import replace
from math import pi, sqrt
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

from .aircraft import AERO_KEYS, installed_loads, read_aircraft, require_analysis, snapshot_aircraft
from .cases import numeric, read_rotor, write_csv, write_json
from .rotor import solve

G = 9.80665
VARIABLES = {'mass_kg', 'altitude_m', 'main_radius_m', 'main_rpm', 'tail_radius_m', 'tail_rpm', 'tail_arm_m'}


def atmosphere(altitude):
    temperature = 288.15 - .0065 * altitude
    pressure = 101325 * (temperature / 288.15)**(G/(287.05287*.0065))
    return dict(temperature_k=temperature, density_kg_m3=pressure/(287.05287*temperature),
                speed_of_sound_m_s=sqrt(1.4*287.05287*temperature),
                dynamic_viscosity_pa_s=1.716e-5*(temperature/273.15)**1.5*(273.15+110.4)/(temperature+110.4))


def apply_design(aircraft, case):
    if 'mass_kg' in case:
        aircraft['mass_properties']['mass_kg'] = numeric(case, 'mass_kg', .01, 1e6)
    for rotor in aircraft['rotors']:
        role = rotor['role']
        if role+'_radius_m' in case:
            rotor['radius_m'] = numeric(case, role+'_radius_m', .03, 30)
        if role+'_rpm' in case:
            rotor['defaults']['rpm'] = numeric(case, role+'_rpm', *rotor['limits']['rpm'])
        if 'radial_stations' in case:
            rotor['defaults']['radial_stations'] = numeric(case, 'radial_stations', 8, 2000, integer=True)
        if role == 'tail' and 'tail_arm_m' in case:
            rotor['position_m'][0] = aircraft['mass_properties']['cg_m'][0] - numeric(case, 'tail_arm_m', .01, 100)


def component_loads(aircraft, rotor, summary):
    installed = installed_loads(aircraft, rotor, summary)
    return dict(summary=summary, **installed)


def balance(aircraft, components):
    weight = aircraft['mass_properties']['mass_kg'] * G
    download = aircraft['hover']['download_fraction'] * components['main']['summary']['thrust_n']
    force = np.array([0., 0., weight + download])
    moment = np.zeros(3)
    for component in components.values():
        force += component['force_body_n']
        moment += component['moment_cg_body_nm']
    return force, moment, download


def run_budget(case, base, output):
    start = perf_counter()
    allowed = {'schema_version','model','analysis','aircraft_json','requested_duration_s','radial_stations',*VARIABLES}
    if set(case)-allowed:
        raise ValueError(f'整机工况未识别字段：{sorted(set(case)-allowed)}')
    if not isinstance(case.get('aircraft_json'), str):
        raise ValueError('需要 aircraft_json。')
    source = (base / case['aircraft_json']).resolve()
    aircraft = read_aircraft(source)
    require_analysis(aircraft, case.get('analysis'))
    altitude = numeric(case, 'altitude_m', 0, 11000)
    duration = numeric(case, 'requested_duration_s', .001, 1e9)
    apply_design(aircraft, case)
    copied = snapshot_aircraft(aircraft, source.parent, output)
    # Save early so both success and failure carry portable, actual inputs.
    snapshot = dict(case, aircraft_json='aircraft.json')
    write_json(output/'case.json', snapshot)
    plant = aircraft['powerplant']
    if not plant['altitude_m'][0] <= altitude <= plant['altitude_m'][-1]:
        raise ValueError('高度超出输入可用功率曲线范围；不外推。')
    air = atmosphere(altitude)
    selected = {r['role']: r for r in copied['rotors']}
    main, tail = selected['main'], selected['tail']
    if main['thrust_axis_body'][2] >= -.5:
        raise ValueError('主桨推力轴需主要向上（axis_z < -0.5）。')
    arm = np.asarray(tail['position_m']) - aircraft['mass_properties']['cg_m']
    if abs(np.cross(arm, tail['thrust_axis_body'])[2]) < .01:
        raise ValueError('尾桨偏航推力臂不足 0.01 m。')
    rotors = {}
    for role, data in selected.items():
        spec = {key:data[key] for key in ('blade_count','radius_m','pitch_reference_r_over_R',
                   'geometry_csv','polar_csv','polar_json',*AERO_KEYS) if key in data}
        spec.update(data['defaults'], axial_speed_m_s=0., density_kg_m3=air['density_kg_m3'],
                    speed_of_sound_m_s=air['speed_of_sound_m_s'],dynamic_viscosity_pa_s=air['dynamic_viscosity_pa_s'])
        rotors[role], _ = read_rotor(spec, output)
    weight = aircraft['mass_properties']['mass_kg']*G
    scale = np.array([weight, weight*main['radius_m']])
    low, high = np.array([selected[r]['limits']['collective_deg'] for r in ('main','tail')]).T
    initial = np.array([rotors[r].collective_deg for r in ('main','tail')])
    evaluations, invalid = 0, []
    best = None

    def evaluate(angles):
        nonlocal evaluations, best
        evaluations += 1
        components, radial = {}, {}
        for role, angle in zip(('main','tail'), angles):
            summary, columns, rows = solve(replace(rotors[role], collective_deg=float(angle)))
            if not all(np.isfinite(value) for value in summary.values()):
                raise ValueError('旋翼解包含非有限值。')
            components[role] = component_loads(aircraft, selected[role], summary)
            radial[role] = (columns, rows)
        force, moment, download = balance(aircraft, components)
        residual = np.array([force[2], moment[2]]) / scale
        if best is None or np.linalg.norm(residual) < best[0]:
            best = (np.linalg.norm(residual), angles.copy(), residual.copy())
        return residual, components, radial, force, moment, download

    # A normal positive-thrust branch near the supplied default is sought.
    # Domain errors terminate a trial; no artificial aerodynamic loads are substituted.
    fit = None
    for seed in (initial, low+.35*(high-low), low+.65*(high-low), low+.85*(high-low)):
        try:
            candidate = least_squares(lambda x:evaluate(x)[0], np.clip(seed,low+1e-7,high-1e-7),
                                      bounds=(low,high), x_scale='jac', ftol=1e-10, xtol=1e-10,
                                      gtol=1e-10, max_nfev=100)
            if np.max(np.abs(candidate.fun)) <= 1e-4:
                fit = candidate
                break
        except ValueError as error:
            invalid.append(str(error))
    diagnostic = dict(evaluations=evaluations, invalid_trials=sorted(set(invalid)),
        scaled_tolerance=1e-4, branch_policy='bounded local solve near default, then 35/65/85% seeds; not exhaustive',
        best_collective_deg=None if best is None else best[1].tolist(),
        best_scaled_residual=None if best is None else best[2].tolist())
    if fit is None:
        return dict(status='failed', solver_status='failed', analysis='hover_budget',
            support_status='not_established', design_limits_status='not_evaluated', evidence_status='model_estimate',
            diagnostics=diagnostic, error='未在给定总距区间和翼型数据域内闭合重量/反扭矩；检查目标载荷、转速、安装符号与限位。'), snapshot
    residual, components, radial, force, moment, download = evaluate(fit.x)
    for role, (columns, rows) in radial.items():
        write_csv(output/f'{role}-radial.csv', columns, rows)
    power_main, power_tail = [components[r]['summary']['power_w'] for r in ('main','tail')]
    loss = power_main*(1/main['transmission_efficiency']-1) + power_tail*(1/tail['transmission_efficiency']-1)
    required = power_main+power_tail+loss+plant['accessory_power_w']
    continuous = float(np.interp(altitude, plant['altitude_m'], plant['continuous_power_w']))
    short = float(np.interp(altitude, plant['altitude_m'], plant['short_time_power_w']))
    short_allowed = duration <= plant['short_time_duration_s']
    margin = (short if short_allowed else continuous) - required
    violations = []
    if margin < 0: violations.append('requested_duration_power_exceeded')
    for role, data in components.items():
        violations.extend(f'{role}_{key}_exceeded' for key,value in data['margins'].items() if value < 0)
    summary = dict(mass_kg=aircraft['mass_properties']['mass_kg'], altitude_m=altitude,
        weight_n=weight, download_n=download, main_power_w=power_main, tail_power_w=power_tail,
        transmission_loss_w=loss, accessory_power_w=plant['accessory_power_w'], required_power_w=required,
        continuous_available_w=continuous, short_time_available_w=short, continuous_margin_w=continuous-required,
        short_time_margin_w=short-required, duration_margin_w=margin,
        tail_side_force_n=components['tail']['force_body_n'][1],
        disk_loading_n_m2=components['main']['summary']['thrust_n']/(pi*main['radius_m']**2),
        max_scaled_balance_residual=float(np.max(np.abs(residual))))
    for role in ('main','tail'):
        for key in ('thrust_n','torque_nm','collective_deg','rpm','tip_speed_m_s'):
            summary[role+'_'+key] = components[role]['summary'][key]
    result = dict(status='converged', solver_status='converged', analysis='hover_budget', summary=summary,
        support_status='within_budget_input_domain', design_limits_status='exceeded' if violations else 'within_supplied_limits',
        feasible=not violations, violations=violations, evidence_status='model_estimate', atmosphere=air,
        components=components, residual_force_body_n=force.tolist(), residual_moment_body_nm=moment.tolist(),
        scaled_budget_residual=residual.tolist(), short_time_rating_applicable=short_allowed,
        requested_duration_s=duration, short_time_duration_s=plant['short_time_duration_s'],
        diagnostics=diagnostic, elapsed_s=perf_counter()-start,
        scope='hover power/load budget: Fz and Mz closed; not full six-axis trim',
        backend='Python / isolated axial rotors + installed loads + bounded hover budget',
        warnings=['侧力、滚转和俯仰未配平；下载施于重心。',
                  '模型估算：固定桨叶轴流、无主尾桨互扰；翼型与动力估计见输入 provenance。'],
        validation_basis=['docs/hover-budget.md','docs/xv15-validation.md','docs/caradonna-tung-validation.md'])
    write_csv(output/'budget.csv', ['quantity','value'], summary.items())
    write_report(result, output)
    return result, snapshot


def write_report(result, output):
    s = result['summary']
    lines = ['# 悬停功率与载荷预算', '', '范围：无地效、静止空气、规定转速；垂向力和偏航力矩闭合。',
        '', f"求解：{result['solver_status']}；数据域：{result['support_status']}；设计限制：{result['design_limits_status']}；证据：模型估算。", '',
        '|项目|值|', '|---|---:|']
    lines.extend(f'|{key}|{value:.8g}|' for key,value in s.items())
    lines.extend(['',f"机体系剩余力 N：{result['residual_force_body_n']}",
                  f"重心剩余力矩 N·m：{result['residual_moment_body_nm']}", '',
                  '完整输入、来源及限制见 aircraft.json；case.json 可通过 run 命令离线复算。',
                  '半径变化保持实际弦长与扭转，径向几何站按 r/R 同比例伸缩。'])
    (output/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
