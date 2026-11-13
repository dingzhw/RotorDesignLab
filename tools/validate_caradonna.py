"""Fixed-collective radial load validation with separate same-thrust diagnostics."""
import argparse
from dataclasses import replace
import hashlib
import json
from math import pi
import os
from pathlib import Path
from tempfile import gettempdir

import numpy as np

from rotordesignlab import __version__
from rotordesignlab.airfoils import AirfoilGrid
from rotordesignlab.cases import read_case,read_rotor,write_csv,write_json
from rotordesignlab.inverse import solve_target
from rotordesignlab.rotor import solve
from tools.prepare_caradonna import FREE,FIXED,make_airfoil


def observables(rotor, answer):
    _,columns,rows=answer
    data=dict(zip(columns,np.array(list(rows)).T))
    radius=data['r_m'];cone=np.cos(np.deg2rad(rotor.precone_deg))
    ut=rotor.omega*radius*cone;up=(rotor.axial_speed+data['induced_speed_m_s'])*cone
    ratio=(ut**2+up**2)/(rotor.omega*radius)**2
    alpha=np.deg2rad(data['alpha_deg'])
    normalizer=.5*rotor.density*(rotor.omega*radius)**2*data['chord_m']*data['dr_m']*rotor.blades
    return dict(r_over_R=radius/rotor.radius,
        rotor_normal_coefficient=data['dthrust_n']/normalizer,
        chord_normal_coefficient=ratio*(data['cl']*np.cos(alpha)+data['cd']*np.sin(alpha)),
        relative_flow_lift_coefficient=ratio*data['cl'],
        reynolds=rotor.density*np.hypot(ut,up)*data['chord_m']/1.7894e-5,
        **data)


def pressure_check(source):
    data=np.genfromtxt(source/'pressure-r080.csv',delimiter=',',names=True,dtype=None,encoding='utf-8')
    upper=data[data['surface']=='upper'];lower=data[data['surface']=='lower']
    # Explicit endpoint assumptions: LE pressure continuous, TE Cp=0 on both sides.
    xu=np.r_[upper['x_over_c'],1];pu=np.r_[upper['minus_cp'],0]
    xl=np.r_[0,lower['x_over_c'],1];pl=np.r_[pu[0],lower['minus_cp'],0]
    cn=float(np.trapezoid(pu,xu)-np.trapezoid(pl,xl))
    return dict(chord_normal_coefficient=cn,reported_cl=.2886,
        difference_pct=100*(cn/.2886-1),
        method='Linear trapezoidal Cp integration; shared LE Cp; both TE Cp=0. Sign/scale diagnostic only.')


def run(source,out):
    out.mkdir(parents=True,exist_ok=False)
    rotor,_=read_rotor(read_case(source/'hover.json'),source)
    reference=np.genfromtxt(source/'reference.csv',delimiter=',',names=True)
    rr=reference['r_over_R'];actual=reference['cl_reported']
    comparisons=[];summaries={};curves={};models={}
    for name,model in [('uniform',replace(rotor,inflow_model='uniform',tip_loss='none')),('annular',rotor)]:
        models[name]=model
    scale=rotor.density*pi*rotor.radius**2*(rotor.omega*rotor.radius)**2
    trimmed,answer,diagnostic=solve_target(rotor,
        dict(thrust_n=.00460*scale,solve_for='collective_deg',bounds=[6,10]),
        dict(collective_deg=[2,14],rpm=[600,1300]))
    models['annular_same_CT']=trimmed
    for name,model in models.items():
        answer=solve(model);summary=answer[0];radial=observables(model,answer)
        curves[name]=radial
        write_json(out/(name+'.json'),summary)
        write_csv(out/(name+'-radial.csv'),list(radial),zip(*radial.values()))
        values=np.interp(rr,radial['r_over_R'],radial['rotor_normal_coefficient'])
        relative=100*(values/actual-1)
        projections=[]
        for i,r in enumerate(rr):
            row=dict(model=name,r_over_R=float(r),reference_cl=float(actual[i]),
                rotor_normal_coefficient=float(values[i]),error_pct=float(relative[i]))
            for key in ('chord_normal_coefficient','relative_flow_lift_coefficient','reynolds','mach','alpha_deg'):
                row[key]=float(np.interp(r,radial['r_over_R'],radial[key]))
            projections.extend([abs(row[key]/row['rotor_normal_coefficient']-1)*100
                for key in ('chord_normal_coefficient','relative_flow_lift_coefficient')])
            comparisons.append(row)
        summaries[name]=dict(ct=summary['thrust_coefficient'],ct_error_pct=100*(summary['thrust_coefficient']/.00460-1),
            collective_deg=model.collective_deg,radial_rmse=float(np.sqrt(np.mean((values-actual)**2))),
            radial_mape_pct=float(np.mean(np.abs(relative))),max_abs_radial_error_pct=float(np.max(np.abs(relative))),
            max_projection_difference_pct=max(projections),reynolds_at_stations=[float(v) for v in np.interp(rr,radial['r_over_R'],radial['reynolds'])])
    write_csv(out/'comparison.csv',list(comparisons[0]),([row[key] for key in comparisons[0]] for row in comparisons))
    grid=[];last=None
    for count in (240,480,960):
        model=replace(rotor,stations=count);answer=solve(model);data=observables(model,answer)
        summary=answer[0];values=np.interp(rr,data['r_over_R'],data['rotor_normal_coefficient'])
        row=dict(stations=count,**{key:summary[key] for key in ('thrust_n','torque_nm','power_w')})
        row.update({f'cl_{r:.2f}':float(v) for r,v in zip(rr,values)})
        if last is not None:changes={key:abs(row[key]/last[key]-1) for key in row if key!='stations'}
        grid.append(row);last=row
    assert max(changes.values()) < .002, changes
    write_csv(out/'grid.csv',list(grid[0]),([row[key] for key in grid[0]] for row in grid))
    variations=[('no_PG',replace(rotor,airfoil_grid=AirfoilGrid(make_airfoil(FREE,pg=False)))),
        ('fixed_transition',replace(rotor,airfoil_grid=AirfoilGrid(make_airfoil(FIXED,name='60-W grit')))),
        ('no_tip_loss',replace(rotor,tip_loss='none')),('cone_0',replace(rotor,precone_deg=0))]
    for root in (.1,.243):
        geometry=rotor.geometry.copy();geometry[0,0]=root
        variations.append((f'root_{root}',replace(rotor,geometry=geometry)))
    sensitivity=[]
    for name,model in variations:
        answer=solve(model);data=observables(model,answer)
        values=np.interp(rr,data['r_over_R'],data['rotor_normal_coefficient'])
        sensitivity.append(dict(change=name,ct=answer[0]['thrust_coefficient'],
            ct_error_pct=100*(answer[0]['thrust_coefficient']/.0046-1),
            radial_mape_pct=float(np.mean(np.abs(values/actual-1))*100),
            **{f'cl_{r:.2f}':float(v) for r,v in zip(rr,values)}))
    write_csv(out/'sensitivity.csv',list(sensitivity[0]),([row[key] for key in sensitivity[0]] for row in sensitivity))
    checks=dict(solver_version=__version__,status='comparison_completed',engineering_accuracy_qualified=False,
        reference_ct=.00460,models=summaries,grid_relative_change_480_960=changes,
        same_CT_relative_error=diagnostic['relative_thrust_error'],pressure_check=pressure_check(source),
        inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()},
        code={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
              [Path('tools/validate_caradonna.py'),Path('tools/prepare_caradonna.py')]+list(Path('rotordesignlab').glob('*.py'))})
    write_json(out/'checks.json',checks)
    os.environ.setdefault('MPLCONFIGDIR',str(Path(gettempdir())/'rotordesignlab-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.4),layout='constrained')
    axes[0].scatter(rr,actual,color='black',marker='o',label='Experiment: Table 17',zorder=5)
    for name,color,label in [('uniform','tab:blue','Uniform, 8 deg'),('annular','tab:red','Annular + Prandtl, 8 deg'),
                             ('annular_same_CT','tab:green','Annular, same CT (diagnostic)')]:
        curve=curves[name];style='--' if 'same' in name else '-'
        axes[0].plot(curve['r_over_R'],curve['rotor_normal_coefficient'],style,color=color,label=label)
        points=[row for row in comparisons if row['model']==name]
        axes[1].plot(rr,[row['error_pct'] for row in points],style+'o',color=color,label=label)
    axes[0].set(xlabel='r/R',ylabel='Section load coefficient (local rotational q)',xlim=(.4,1),ylim=(0,.6))
    axes[0].legend(fontsize=8);axes[1].axhline(0,color='black',linewidth=.7)
    axes[1].set(xlabel='r/R',ylabel='Difference from Table 17 (%)',xlim=(.45,1))
    for ax in axes:ax.grid(alpha=.3)
    fig.suptitle('Caradonna–Tung hover: 1250 rpm, tip Mach 0.439, NACA 0012')
    fig.savefig(out/'comparison.png',dpi=150);fig.savefig(out/'comparison.svg');plt.close(fig)
    svg=out/'comparison.svg';svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
    print(json.dumps(dict(models=summaries,grid=changes,pressure=checks['pressure_check']),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=Path('validation/caradonna-tung'))
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();run(args.source,args.out)
