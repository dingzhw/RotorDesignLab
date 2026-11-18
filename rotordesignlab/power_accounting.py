"""Auditable steady shaft-power ledger; never changes the solver's loads."""
from math import pi
import numpy as np
from .cases import write_csv, write_json


POWER_TERMS = {
    'main_power_w': '主桨气动轴功率', 'tail_power_w': '尾桨气动轴功率',
    'transmission_loss_w': '传动损失', 'accessory_power_w': '附件耗功',
    'required_power_w': '动力侧需用轴功率', 'continuous_margin_w': '连续功率余量',
    'short_time_margin_w': '短时功率余量', 'duration_margin_w': '本次持续时间功率余量',
}


def ledger(aircraft, case, result):
    """Rotor positive drive Q; P=Omega*Q. Body reaction torque has opposite sign.

    All powers are W. Rotor power is at the rotor shaft; availability/accessories
    are at the powerplant output. Passive download has no separate shaft motor:
    its induced demand is already present in the solved rotor power.
    """
    summary = result['summary']
    budget = result['analysis'] == 'hover_budget'
    rows = []
    for role in ('main', 'tail'):
        rotor = next(r for r in aircraft['rotors'] if r['role'] == role)
        power = summary[role+'_power_w']
        omega = rotor['defaults']['rpm']*pi/30
        efficiency = rotor['transmission_efficiency']
        arm = np.asarray(rotor['position_m'])-np.asarray(aircraft['mass_properties']['cg_m'])
        component = result['components'][role]
        rows.append(dict(role=role, shaft_power_w=power, torque_nm=summary[role+'_torque_nm'],
                         omega_rad_s=omega, efficiency=efficiency, input_power_w=power/efficiency,
                         loss_w=power*(1/efficiency-1),
                         omega_q_residual_w=power-omega*summary[role+'_torque_nm'],
                         inflow=(rotor.get('inflow_model', 'uniform') if budget else 'steady_pitt_peters'),
                         tip_loss=(rotor.get('tip_loss', 'none') if budget else 'none'),
                         flap=('fixed_axial' if budget else rotor['flight']['flapping']['mode']),
                         precone_deg=(rotor.get('precone_deg', 0.) if budget else rotor['flight']['flapping']['precone_deg']),
                         position_m=rotor['position_m'], thrust_axis_body=rotor['thrust_axis_body'],
                         yaw_thrust_arm_m=float(np.cross(arm, rotor['thrust_axis_body'])[2]),
                         force_body_n=component['force_body_n'], moment_cg_body_nm=component['moment_cg_body_nm'],
                         solved_flap_deg=component.get('flap_deg'),
                         collective_deg=summary[role+'_collective_deg']))
    plant = aircraft['powerplant']
    altitude = case['altitude_m']
    continuous = float(np.interp(altitude, plant['altitude_m'], plant['continuous_power_w']))
    short = float(np.interp(altitude, plant['altitude_m'], plant['short_time_power_w']))
    applicable = case['requested_duration_s'] <= plant['short_time_duration_s']
    selected = short if applicable else continuous
    computed = sum(r['input_power_w'] for r in rows)+plant['accessory_power_w']
    return dict(components=rows, accessory_power_w=plant['accessory_power_w'],
                required_power_w=summary['required_power_w'], sum_residual_w=summary['required_power_w']-computed,
                continuous_available_w=continuous, short_time_available_w=short, selected_available_w=selected,
                rating='short_time' if applicable else 'continuous',
                requested_duration_s=case['requested_duration_s'], short_time_duration_s=plant['short_time_duration_s'],
                margin_residual_w=summary['duration_margin_w']-(selected-computed),
                download=result['download_model'],
                download_force_body_n=([0., 0., summary['download_n']] if budget else result['components']['download']['force_body_n']),
                residual_force_body_n=result['residual_force_body_n'], residual_moment_body_nm=result['residual_moment_body_nm'],
                attitude_deg=[summary.get('roll_deg', 0.), summary.get('pitch_deg', 0.)],
                cyclic_deg=[summary.get('main_cos_deg', 0.), summary.get('main_sin_deg', 0.)],
                nonrotor_loads={key: value for key, value in result['components'].items() if key not in ('main', 'tail')},
                scope='稳态气动轴功率；下载和机身/尾翼通过载荷改变旋翼需求，不重复相加。',
                transient_scope='未包含转速变化、挥舞储能变化及瞬态轴端传递功率；不能用此账目判定瞬态动力峰值。')


def attach(aircraft, case, result, output):
    accounting = ledger(aircraft, case, result)
    result['power_accounting'] = accounting
    write_json(output/'power-accounting.json', accounting)
    rows = []
    for row, title in zip(accounting['components'], ('主桨', '尾桨')):
        rows.extend([(title+'气动轴功率', row['shaft_power_w']/1000),
                     (title+'传动损失', row['loss_w']/1000)])
    rows.extend([(POWER_TERMS[k], result['summary'][k]/1000) for k in
                 ('accessory_power_w', 'required_power_w', 'continuous_margin_w', 'short_time_margin_w', 'duration_margin_w')])
    write_csv(output/'power-ledger.csv', ['功率项目', '数值_kW'], rows)
    lines = ['\n## 功率口径', '', accounting['scope'], accounting['transient_scope'], '',
             '|功率项目|kW|', '|---|---:|']
    lines.extend(f'|{name}|{value:.6f}|' for name, value in rows)
    rating = '短时' if accounting['rating'] == 'short_time' else '连续'
    lines.extend(['', f"本次持续{case['requested_duration_s']:g} s，采用{rating}可用功率；短时额定限时{accounting['short_time_duration_s']:g} s。",
                  'P=ΩQ采用旋翼正驱动扭矩；不使用机体反扭矩的负号。'])
    with (output/'report.md').open('a', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
