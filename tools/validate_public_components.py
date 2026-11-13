"""Public component intercomparison; no flight/experiment accuracy claim."""
import argparse
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from rotordesignlab.cases import read_case,run_case,write_csv,write_json
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.airframe import airframe_loads

ROOT=Path(__file__).resolve().parents[1]


def export_source(out):
    out.mkdir(parents=True,exist_ok=True);d=loadmat(ROOT/'data/H60fuselage.mat');rows=[]
    for group,angle,keys in [(1,'FUSEAOA',['FUSEDA','FUSELA','FUSEMA',None]),
                             (2,'FUSEBETA',['FUSEYB','FUSELB','FUSERB','FUSENB']),
                             (3,'FUSEABETA',['FUSEDB',None,'FUSEMB',None])]:
        for i,a in enumerate(d[angle].ravel()):
            rows.append([group,a,*[d[k].ravel()[i] if k else 0 for k in keys]])
    write_csv(out/'fuselage-source.csv',['group','angle','c1','c2','c3','c4'],rows)


def validate(out):
    base=ROOT/'examples/public-helicopter';a=read_aircraft(base/'uh60-public.json')
    ref=np.loadtxt(out/'julia-fuselage.csv',delimiter=',',skiprows=1);errors=[]
    for row in ref:
        r=airframe_loads(a,row[:3],1.225,np.zeros(3))['fuselage']
        errors.append(float(np.max(abs(np.r_[r['force_body_n'],r['moment_cg_body_nm']]-row[3:]))))
    assert max(errors)<1e-8,errors
    case=read_case(base/'uh60-public-case.json');grid=[];last=None
    for n,az in [(80,36),(160,72),(320,144)]:
        r=run_case(dict(case,speed_m_s=20,radial_stations=n,azimuth_stations=az),base,out/f'grid-{n}')
        assert r['status']=='converged',r
        s=r['summary'];grid.append(dict(radial=n,azimuth=az,**s))
        if last:changes={k:abs(s[k]/last[k]-1) for k in s if k.endswith(('_power_w','_thrust_n','_torque_nm'))}
        last=s
    assert max(changes.values())<.002,changes
    records=[]
    for speed in [0,20,40,50]:
        r=run_case(dict(case,speed_m_s=speed),base,out/f'speed-{speed}')
        records.append(dict(speed_m_s=speed,status=r['status'],error=r.get('error',''),summary=r.get('summary')))
        assert r['status']==('converged' if speed<=20 else 'failed'),r
    comparisons=[]
    import csv
    for row in list(csv.DictReader((ROOT/'validation/trim/tm85890-table4.csv').open()))[:3]:
        kt=float(row['eas_kt']);r=run_case(dict(case,speed_m_s=kt*1852/3600),base,out/f'tm-{kt:g}')
        assert r['status']=='converged',r
        s=r['summary'];comparisons.append(dict(eas_kt=kt,**{key+'_difference_deg':s[key]-float(row[key]) for key in ['pitch_deg','roll_deg']}))
    write_csv(out/'grid.csv',list(grid[0]),(r.values() for r in grid))
    write_json(out/'checks.json',dict(julia_fuselage_max_abs_error=max(errors),last_grid_relative_change=changes,
        envelope=records,tm85890_table4= comparisons,physical_accuracy_accepted=False,
        remaining_gaps=['Tail Re table excludes some 40/50 m/s elements','Tail teeter/blockage/swirl absent',
          'HT frozen collective schedule; not original stabilator feedback','Legacy aero table measurement provenance incomplete',
          'Download and power availability remain estimates']))
    print({'fuselage_max_error':max(errors),'grid_max_change':max(changes.values()),'comparison':comparisons},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--export-only',action='store_true')
    args=p.parse_args();export_source(args.out)
    if not args.export_only:validate(args.out)
