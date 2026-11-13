"""Numerical and public-model checks for the explicitly reduced dynamics."""
import argparse,shutil,socket
from pathlib import Path
from unittest.mock import patch
import numpy as np
from rotordesignlab.cases import read_case,run_case,write_json,write_csv
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.trim import TrimSystem
from rotordesignlab.dynamics import ReducedDynamics,STATES,CONTROLS,step_response
from rotordesignlab.steady_rotor import pitt_peters

ROOT=Path(__file__).resolve().parents[1]


def load_plant(out):
    case=read_case(out/'trim/case.json');a=read_aircraft(out/'trim/aircraft.json');r=read_case(out/'result.json')['trim']
    plant=ReducedDynamics(TrimSystem(a,out/'trim',case),r['diagnostics']['solved_state'],r['velocity_body_m_s'])
    a=np.loadtxt(out/'A.csv',delimiter=',',skiprows=1,usecols=range(1,16))
    b=np.loadtxt(out/'B.csv',delimiter=',',skiprows=1,usecols=range(1,5))
    return plant,a,b


def validate(out):
    out.mkdir(parents=True,exist_ok=False);base=ROOT/'examples/public-helicopter';records={}
    ref=np.loadtxt(ROOT/'validation/open-loop/julia-inflow-dynamics.csv',delimiter=',',skiprows=1);errors=[]
    for row in ref:
        rate,_=pitt_peters(row[6:9],row[:3],row[3],row[4:6],dynamic=True,omega=row[9])
        errors.append(float(abs(rate-row[10:]).max()))
    assert max(errors)<1e-9;records['julia_frozen_flow_max_abs_difference']=max(errors)
    for name in ['synthetic','uh60-public']:
        case=read_case(base/f'{name}-case.json');points=[]
        for speed in [0,20]:
            target=out/f'{name}-{speed}';r=run_case(dict(case,analysis='linearize',speed_m_s=speed),base,target)
            assert r['status']=='converged',r
            points.append(dict(speed_m_s=speed,**r['summary'],elapsed_s=r['elapsed_s'],difference_check=r['linearization']['derivative_check']))
            print(name,speed,'linearized',r['summary'],flush=True)
        records[name]=dict(points=points,responses=[])
        plant,a,b=load_plant(out/f'{name}-20');scale=np.array([10.]*3+[.1]*6+[.05]*6)
        # 0.2 seconds isolates local small-disturbance checks from long-term divergence.
        h=.001 if name=='synthetic' else .01;duration=.2
        for index,control in enumerate(CONTROLS):
            histories=[]
            for label,amplitude,step in [('coarse',.05,h),('fine',.05,h/2),('half',.025,h/2)]:
                history=step_response(plant,a,b,index,amplitude,duration,step);histories.append(history)
                write_csv(out/f'{name}-{control}-{label}.csv',['time_s',*[k+'_nonlinear' for k in STATES],*[k+'_linear' for k in STATES]],history)
            coarse,fine,half=histories
            component_peak=np.max(abs(fine[:,1:10]),axis=0)
            denominator=np.maximum(component_peak,1e-5*np.array([10.]*3+[.1]*6))
            step_error=float(np.max(np.max(abs(coarse[:,1:10]-fine[::2,1:10]),axis=0)/denominator))
            errors=[float(np.max(np.linalg.norm((v[:,1:16]-v[:,16:31])/scale,axis=1))) for v in (fine,half)]
            ratio=errors[1]/max(errors[0],1e-20)
            record=dict(control=control,duration_s=duration,coarse_step_s=h,time_step_relative_error=step_error,
                        nonlinear_linear_error=errors,half_amplitude_error_ratio=ratio,
                        time_step_pass=step_error<=.01,amplitude_pass=ratio<.65)
            records[name]['responses'].append(record);print(name,record,flush=True)
        assert all(r['time_step_pass'] and r['amplitude_pass'] for r in records[name]['responses']),records[name]
    # Directory relocation + Python-network-disabled exported input replay.
    shutil.copytree(out/'synthetic-20',out/'relocated')
    with patch.object(socket,'socket',side_effect=RuntimeError('offline validation')):
        replay=run_case(read_case(out/'relocated/case.json'),out/'relocated',out/'offline-replay')
    assert replay['status']=='converged',replay
    replay_a=np.loadtxt(out/'offline-replay/A.csv',delimiter=',',skiprows=1,usecols=range(1,16))
    original_a=np.loadtxt(out/'synthetic-20/A.csv',delimiter=',',skiprows=1,usecols=range(1,16))
    np.testing.assert_allclose(replay_a,original_a,rtol=1e-9,atol=1e-9)
    records['relocation_python_offline_replay']=True
    write_json(out/'checks.json',records)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);validate(p.parse_args().out)
