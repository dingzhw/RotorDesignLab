"""Qualified load-derivative comparison, not an aircraft acceptance criterion."""
import argparse,csv
from pathlib import Path
import numpy as np
from rotordesignlab.cases import read_case,run_case,write_csv,write_json

ROOT=Path(__file__).resolve().parents[1]


def compare(out):
    out.mkdir(parents=True,exist_ok=False);base=ROOT/'examples/public-helicopter';case=read_case(base/'uh60-public-case.json')
    references=list(csv.DictReader((ROOT/'validation/open-loop/tm85890-selected-derivatives.csv').open()));records=[]
    for ref in references:
        speed=float(ref['eas_kt']);target=out/f'{speed:g}kt'
        r=run_case(dict(case,analysis='linearize',speed_m_s=speed*1852/3600),base,target)
        assert r['status']=='converged',r
        a=np.loadtxt(target/'A.csv',delimiter=',',skiprows=1,usecols=range(1,16))
        relaxed=a[:9,:9]-a[:9,9:]@np.linalg.solve(a[9:,9:],a[9:,:9])
        # Xu and Zw are pure load derivatives at zero body rate; Ixy=Iyz=0,
        # so Mq=angular acceleration derivative q_dot/q (no pitch inertial cross term).
        for label,i,j in [('Xu',0,0),('Zw',2,2),('Mq',4,4)]:
            reference=float(ref[label+'_per_s'])
            records.append(dict(eas_kt=speed,derivative=label,unit='1/s',reference=reference,
                fixed_inflow=float(a[i,j]),relaxed_inflow=float(relaxed[i,j]),
                relaxed_difference=float(relaxed[i,j]-reference),relaxed_error_pct=float((relaxed[i,j]/reference-1)*100)))
    write_csv(out/'comparison.csv',records[0].keys(),(r.values() for r in records))
    write_json(out/'scope.json',dict(source='https://ntrs.nasa.gov/citations/19840015585',
        reference='TM-85890 Tables 5,6,8 printed pp16,17,19; derivative definition printed p8; visually checked source pages',
        reference_configuration='level flight; PBA ON, active stabilator; governor OFF; perturbations 1 ft/s and 5 deg/s',
        current_configuration='raw blade-pitch controls, no PBA; collective-reference-frozen stabilator schedule; quasi-steady flap; small local derivatives',
        conventions='Xu,Zw: per-mass load derivatives, Mq: per Iyy moment derivative. No inch-to-blade-control conversion. Frozen and zero-frequency inflow-eliminated columns kept separate.',
        assumptions='Sea-level ISA and EAS=TAS; reference table altitude unspecified. No tuning to these derivatives.',
        physical_accuracy_accepted=False))
    print(records,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);compare(p.parse_args().out)
