"""Rebuild public/synthetic hover templates, without private aircraft inputs."""
from copy import deepcopy
from math import pi, sin, cos, radians
from pathlib import Path

from rotordesignlab.cases import read_case, write_json, write_csv


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / 'examples'
    synthetic = read_case(source / 'synthetic-aircraft.json')
    # Materialize the old synthetic inputs to make this folder portable.
    for name in ('synthetic-geometry.csv', 'synthetic-polar.csv'):
        (out / name).write_bytes((source / name).read_bytes())
    synthetic.update(schema_version=2, id='synthetic-hover', name='200 kg 合成无人直升机',
        description='无地效悬停功率与载荷预算；全部参数为合成功能样例。')
    main = synthetic['rotors'][0]
    main.update(role='main', transmission_efficiency=.96)
    tail = deepcopy(main)
    tail.update(id='tail', role='tail', blade_count=2, radius_m=.24,
        geometry_csv='synthetic-tail-geometry.csv', position_m=[-1.7, 0, -.15],
        thrust_axis_body=[0, 1, 0], transmission_efficiency=.93,
        description='合成双叶尾桨', provenance='Synthetic: all dimensions, rpm, limits and installation estimated',
        defaults=dict(rpm=7500, collective_deg=12, radial_stations=240),
        limits=dict(rpm=[4000, 9000], collective_deg=[2, 24], power_w=8000, torque_nm=12))
    synthetic['rotors'].append(tail)
    synthetic['hover'] = dict(download_fraction=.03, provenance='Synthetic download = 0.03 * main thrust; applied at CG')
    synthetic['powerplant'] = dict(altitude_m=[0, 3000, 6000, 11000],
        continuous_power_w=[45000, 36000, 24000, 12000], short_time_power_w=[55000, 44000, 30000, 15000],
        short_time_duration_s=120, accessory_power_w=700,
        provenance='Synthetic shaft-power curves, losses and 120 s rating; not a specific engine')
    write_csv(out / 'synthetic-tail-geometry.csv', ['r_over_R', 'chord_m', 'twist_deg'],
              [[.2,.045,3],[.75,.045,0],[1,.04,-1]])
    write_json(out / 'synthetic.json', synthetic)

    public = deepcopy(synthetic)
    public.update(id='uh60-hover-public', name='UH-60 公开参数预算模板',
        description='J-GenHel 公开几何/安装参数 + 明示工程估计；非 Julia UH-60 动力学复现。',
        provenance='src/H60_constants.jl at baseline 05f3872; see docs/hover-budget.md for conversions and estimated fields')
    public['mass_properties'] = dict(mass_kg=16000*.45359237, cg_m=[0,0,0])
    mr, tr = public['rotors']
    mr.update(blade_count=4, radius_m=26.83*.3048, geometry_csv='uh60-main-geometry.csv',
        polar_csv='uh60-main-estimated-polar.csv', position_m=[(358-341.25)*.0254,0,(248.2-315)*.0254],
        thrust_axis_body=[sin(radians(3)),0,-cos(radians(3))],
        defaults=dict(rpm=27*30/pi, collective_deg=10, radial_stations=240),
        limits=dict(rpm=[200,300],collective_deg=[2,24]),
        description='公开主桨几何；简化气动', provenance='H60_constants: R, NB, chord, twist, OMEGA, ITHSH, FS/WL; limits and efficiency estimated')
    tr.update(blade_count=4, radius_m=5.5*.3048, geometry_csv='uh60-tail-geometry.csv',
        polar_csv='uh60-tail-estimated-polar.csv', position_m=[(358-732)*.0254,-14*.0254,(248.2-324.7)*.0254],
        thrust_axis_body=[0,cos(radians(20)),-sin(radians(20))],
        defaults=dict(rpm=124.62*30/pi,collective_deg=12,radial_stations=240),
        limits=dict(rpm=[1000,1300],collective_deg=[2,24]),
        description='公开尾桨尺寸/安装；根切与转向为显式假设',
        provenance='H60_constants / GenHel: RTR, CHRDTR, twistTR, OmegaTR, CantTR, BLDSTR=4; root=0.2R, rotation_sign=1, limits and efficiency estimated')
    public['hover'] = dict(download_fraction=.03, provenance='Engineering assumption, not a UH-60 measured download')
    public['powerplant'] = dict(altitude_m=[0,3000,6000,11000],
        continuous_power_w=[2400000,1800000,1200000,600000], short_time_power_w=[2800000,2100000,1400000,700000],
        short_time_duration_s=120,accessory_power_w=20000,
        provenance='Illustrative available shaft power only; NOT T700 ratings. Transmission efficiencies .96/.93 estimated')
    twist = [0,0,0,0,-.15,-.95,-1.80,-2.75,-3.55,-4.40,-5.30,-6.15,-7.10,-7.90,-8.80,-9.65,-10.30,-10.75,-12.30,-13.10,-10.9]
    import numpy as np
    root = 3.5/26.83
    stations = [root] + [i/20 for i in range(3,21)]
    write_csv(out/'uh60-main-geometry.csv',['r_over_R','chord_m','twist_deg'],
              [[r,1.73*.3048,float(np.interp(r,np.arange(21)/20,twist))] for r in stations])
    write_csv(out/'uh60-tail-geometry.csv',['r_over_R','chord_m','twist_deg'],
              [[r,.81*.3048,-17.2*r] for r in [.2,.75,1]])
    # Extrapolated linear lift laws are engineering estimates, not measured tables.
    for role,slope,zero in [('main',6.5,-2),('tail',5.73,0)]:
        rows=[]
        for alpha in range(-20,26):
            drag=.008 if role=='main' else .0087-.0216*radians(alpha)+.4*radians(alpha)**2
            rows.append([alpha,slope*radians(alpha-zero),drag])
        write_csv(out/f'uh60-{role}-estimated-polar.csv',['alpha_deg','cl','cd'],rows)
    write_json(out/'uh60-public.json',public)
    for name in ('synthetic','uh60-public'):
        write_json(out/f'{name}-case.json',dict(schema_version=3,model='helicopter',analysis='hover_budget',
            aircraft_json=f'{name}.json',altitude_m=0,requested_duration_s=600))


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1]/'examples'/'hover')
