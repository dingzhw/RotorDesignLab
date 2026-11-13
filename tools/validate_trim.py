"""Reproducible numerical/domain campaign and qualified public model comparison."""
import argparse,csv,hashlib,json,os,platform,shutil
from pathlib import Path
import numpy as np
from rotordesignlab.cases import read_case,run_case,write_json,write_csv
from rotordesignlab.batch import run_batch

ROOT=Path(__file__).resolve().parents[1]


def validate(out):
    out.mkdir(parents=True,exist_ok=False);base=ROOT/'examples/trim';records={};grid=[];envelope=[]
    for name in ('synthetic','uh60-public'):
        case=read_case(base/f'{name}-case.json');answers=[]
        for n,az in [(80,36),(160,72),(320,144)]:
            r=run_case(dict(case,speed_m_s=20,radial_stations=n,azimuth_stations=az),base,out/f'{name}-grid-{n}')
            assert r['status']=='converged',r
            answers.append(r['summary']);grid.append(dict(template=name,radial=n,azimuth=az,elapsed_s=r['elapsed_s'],**r['summary']))
        changes={key:abs(answers[-1][key]/answers[-2][key]-1) for key in answers[-1]
                 if key.endswith(('_thrust_n','_torque_nm','_power_w')) and answers[-2][key]!=0}
        assert max(changes.values())<=.002,changes
        records[name]=dict(last_grid_relative_changes=changes)
        near=[]
        for speed in [0,.0001,10,20,30,40]:
            r=run_case(dict(case,speed_m_s=speed),base,out/f'{name}-speed-{speed}')
            envelope.append(dict(template=name,status=r['status'],solver_status=r['solver_status'],support_status=r['support_status'],
                                 error=r.get('error',''),**dict({'speed_m_s':speed},**r.get('summary',{}))))
            if speed in (0,.0001):
                assert r['status']=='converged',r
                near.append(r['summary'])
        records[name]['zero_speed_power_relative_change']=abs(near[1]['required_power_w']/near[0]['required_power_w']-1)
        assert records[name]['zero_speed_power_relative_change']<1e-4
        spec=dict(schema_version=1,kind='helicopter_trim_sweep',case_json=f'{name}-case.json',axes={'speed_m_s':[0,5,10,15,20]})
        r=run_batch(spec,base,out/f'{name}-speed-sweep');assert r['status']=='converged',r
    for label in ('mass','cg'):
        spec=read_case(base/f'{label}-sweep.json');r=run_batch(spec,base,out/f'{label}-sweep');assert r['status']=='converged',r
    # Published model Table 4: use low-speed entries; later points use another sideslip/roll condition.
    src=out/'tm85890-input';shutil.copytree(base,src)
    a=read_case(src/'uh60-public.json');a['mass_properties']['mass_kg']=16400*.45359237
    a['mass_properties']['cg_m']=[-(360.4-358)*.0254,0,-(247.2-248.2)*.0254]
    a['provenance']+='; Table 1 TM-85890 mass/CG matched; remaining airframe/rotor differences explicitly retained'
    write_json(src/'uh60-public.json',a);case=read_case(src/'uh60-public-case.json')
    comparisons=[]
    with (ROOT/'validation/trim/tm85890-table4.csv').open() as f:table=list(csv.DictReader(f))
    for row in table[:3]:
        kt=float(row['eas_kt']);r=run_case(dict(case,speed_m_s=kt*1852/3600),src,out/f'tm85890-{kt:g}kt')
        assert r['status']=='converged',r
        s=r['summary'];comparison=dict(eas_kt=kt,assumed_altitude_m=0,status=r['status'])
        for key in ('pitch_deg','roll_deg'):
            comparison.update({key+'_reference':float(row[key]),key+'_computed':s[key],key+'_difference':s[key]-float(row[key])})
        comparison['computed_power_w']=s['required_power_w'];comparisons.append(comparison)
    spec=dict(schema_version=1,kind='helicopter_trim_sweep',case_json='synthetic-case.json',
              axes={'speed_m_s':np.linspace(0,20,10).tolist(),'mass_kg':np.linspace(180,220,10).tolist()})
    timing=run_batch(spec,base,out/'timing-100');assert timing['status']=='converged',timing
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:cpu=winreg.QueryValueEx(k,'ProcessorNameString')[0].strip()
    except (ImportError,OSError):cpu=platform.processor()
    records['environment']=dict(cpu=cpu,logical_cpus=os.cpu_count(),platform=platform.platform(),python=platform.python_version(),numpy=np.__version__)
    records['timing']=dict(radial=80,azimuth=36,points=100,elapsed_s=timing['elapsed_s'],target_600s_pass=timing['elapsed_s']<=600,
                           grid_single_point_max_s=max(r['elapsed_s'] for r in grid if r['radial']==80))
    records['public_comparison']=dict(source='https://ntrs.nasa.gov/citations/19840015585',table='Table 4, printed page 15 / PDF page 21',
        kind='mathematical_model_comparison_with_configuration_differences',reference_control_units='inches with PBA/crossfeed; not compared to blade pitch',
        environment_assumption='Sea-level ISA for EAS=TAS; reference table does not specify altitude',
        high_speed_exclusion='At 60/100/140 kt reference roll=0 with nonzero body lateral speed; current trim prescribes body v=0',
        pitch_max_absolute_difference_deg=max(abs(r['pitch_deg_difference']) for r in comparisons),
        roll_max_absolute_difference_deg=max(abs(r['roll_deg_difference']) for r in comparisons),
        physical_accuracy_accepted=False)
    files=[*sorted((ROOT/'rotordesignlab').glob('*.py')),*sorted((ROOT/'examples/trim').glob('*')),
           ROOT/'schemas/aircraft-v2.schema.json',ROOT/'tools/validate_trim.py',ROOT/'validation/trim/tm85890-table4.csv']
    records['input_code_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    for name,rows in [('grid',grid),('envelope',envelope),('tm85890-comparison',comparisons)]:
        headers=list(dict.fromkeys(k for r in rows for k in r));write_csv(out/f'{name}.csv',headers,([r.get(k,'') for k in headers] for r in rows))
    write_json(out/'acceptance.json',records);print(json.dumps({k:v for k,v in records.items() if k!='input_code_sha256'},indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);validate(p.parse_args().out)
