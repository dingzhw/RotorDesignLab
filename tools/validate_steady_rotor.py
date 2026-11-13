"""Public hover reuse and separate steady-operator intercomparison."""
from dataclasses import replace
import json
from pathlib import Path
import argparse
import numpy as np
from rotordesignlab.cases import read_case,read_rotor,write_json
from rotordesignlab.steady_rotor import SteadyRotor,pitt_peters
from rotordesignlab.rotor import solve


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    results={}
    for name in ('xv15','caradonna-tung'):
        base=Path('validation')/name;r,_=read_rotor(read_case(base/'hover.json'),base)
        r=replace(r,inflow_model='uniform',tip_loss='none',stations=240)
        fixed=dict(mode='fixed',hinge_offset_m=0,precone_deg=r.precone_deg,max_flap_deg=15)
        state,data,diag=SteadyRotor(r,fixed,azimuth_stations=36).solve(np.deg2rad([r.collective_deg,0,0]),[0,0,0],gravity=[0,0,0])
        old=solve(r)[0]
        scale=r.density*np.pi*r.radius**2*(r.omega*r.radius)**2
        results[name]=dict(thrust_n=float(data['force'][2]),power_w=data['power'],ct=float(data['force'][2]/scale),
            relative_to_uniform_axial=dict(thrust=float(data['force'][2]/old['thrust_n']-1),power=data['power']/old['power_w']-1),
            inflow=state[:3].tolist(),diagnostics=diag,
            scope='fixed prescribed precone / uniform PP hover; annular performance validation remains separate')
        assert max(abs(v) for v in results[name]['relative_to_uniform_axial'].values())<.002
        if name=='caradonna-tung':results[name]['ct_error_pct']=(results[name]['ct']/.0046-1)*100
    reference=np.loadtxt('runs/v030-pp-julia.csv',delimiter=',',skiprows=1)
    differences=[]
    for row in reference:
        residual,_=pitt_peters(row[5:8],row[:2].tolist()[:1]+[0,row[1]],row[2],row[3:5])
        differences.append(float(np.max(abs(residual))))
    assert max(differences)<1e-10
    write_json(out/'checks.json',dict(public_hover=results,julia_operator_max_abs_difference=max(differences),
        note='Software/model checks. No new forward-flight experiment; no parameter fitting.'))
    print(json.dumps(results,ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
