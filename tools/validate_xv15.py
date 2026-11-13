"""Same-thrust XV-15 validation; no coefficients are fitted to measurements."""
import argparse
import csv
from dataclasses import replace
import hashlib
import json
from math import pi
import os
from pathlib import Path
from tempfile import gettempdir

import numpy as np

from rotordesignlab import __version__
from rotordesignlab.cases import read_case, read_rotor, write_csv, write_json
from rotordesignlab.inverse import solve_target
from rotordesignlab.rotor import solve


def fingerprint(source):
    root=Path(__file__).resolve().parents[1]
    return dict(inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*') if p.is_file()},
        solver={name:hashlib.sha256((root/'rotordesignlab'/name).read_bytes()).hexdigest()
                for name in ('airfoils.py','axial.py','rotor.py','inverse.py','cases.py','__init__.py')})


def run(source, output, resume=False):
    output.mkdir(parents=True,exist_ok=resume)
    hashes=fingerprint(source)
    if resume:
        assert read_case(output/'input-sha256.json')==hashes, 'Inputs or solver changed; use a fresh output directory.'
    else:
        write_json(output/'input-sha256.json',hashes)
    case=read_case(source/'hover.json')
    rotor,_=read_rotor(case,source)
    rotor=replace(rotor,stations=480)
    reference=np.loadtxt(source/'legacy_reference_ct_cq.csv',delimiter=',')
    reference=reference[np.argsort(reference[:,0])]
    with (source/'betzina_fig15.csv').open(encoding='utf-8',newline='') as stream:
        markers=list(csv.DictReader(stream))
    digitization={run:np.array([[float(row['ct_sigma']),float(row['cq_sigma'])] for row in markers if int(row['run'])==run]) for run in (33,51)}
    scale=rotor.density*pi*rotor.radius**2*(rotor.omega*rotor.radius)**2
    def target(model,ct):
        return solve_target(model,dict(thrust_n=float(ct*scale),solve_for='collective_deg',bounds=[4,18]),dict(collective_deg=[-20,55],rpm=[1,30000]))
    rows=[];solutions={}
    for mode in ('uniform','annular'):
        model=replace(rotor,inflow_model=mode,tip_loss='none' if mode=='uniform' else 'prandtl')
        for cts in np.linspace(.06,.12,7):
            row=dict(model=mode,ct_sigma=float(cts),status='failed')
            try:
                name=f'{mode}-{cts:.2f}'
                cached=output/(name+'.json')
                if resume and cached.exists():
                    record=read_case(cached); summary=record['summary']
                    solved=replace(model,collective_deg=summary['collective_deg'])
                    diagnostic=dict(relative_thrust_error=abs(summary['thrust_n']/(cts*.089*scale)-1))
                else:
                    solved,answer,diagnostic=target(model,cts*.089)
                    summary,headers,radial=answer
                    write_json(cached,dict(case=dict(case,collective_deg=solved.collective_deg,
                        radial_stations=480,inflow_model=mode,tip_loss=solved.tip_loss),summary=summary))
                    write_csv(output/(name+'-radial.csv'),headers,radial)
                cq_ref=np.interp(cts,reference[:,0],reference[:,1])*.089
                vector_refs=[float(np.interp(cts,values[:,0],values[:,1])*.089) for values in digitization.values()]
                row.update(status='converged',collective_deg=summary['collective_deg'],ct=summary['thrust_coefficient'],
                    cq=summary['torque_coefficient'],fm=summary['hover_figure_of_merit'],reference_cq=cq_ref,
                    power_error_pct=100*(summary['torque_coefficient']/cq_ref-1),
                    run33_cq=vector_refs[0],run51_cq=vector_refs[1],
                    target_relative_error=diagnostic['relative_thrust_error'])
                solutions[(mode,round(float(cts),2))]=solved
            except ValueError as error:
                row['error']=str(error)
            rows.append(row)
            print(json.dumps(row,ensure_ascii=True),flush=True)
    columns=['model','ct_sigma','status','collective_deg','ct','cq','fm','reference_cq','power_error_pct','run33_cq','run51_cq','target_relative_error','error']
    write_csv(output/'comparison.csv',columns,([row.get(key,'') for key in columns] for row in rows))
    assert all(row['status']=='converged' for row in rows), 'Keep failed rows; investigate before reporting completion.'
    mid=solutions[('annular',.09)]
    grid=[]
    for count in (240,480,960):
        summary=solve(replace(mid,stations=count))[0]
        grid.append(dict(stations=count,**{key:summary[key] for key in ('thrust_n','torque_nm','power_w','hover_figure_of_merit')}))
    changes={key:abs(grid[1][key]/grid[2][key]-1) for key in ('thrust_n','torque_nm','power_w')}
    assert max(changes.values()) < .002
    write_csv(output/'grid.csv',list(grid[0]),([row[key] for key in grid[0]] for row in grid))
    sensitivities=[]
    for label,changed in [('cone_0',dict(precone_deg=0)),('cone_2.5',dict(precone_deg=2.5)),
                          ('axial_0.1',dict(axial_speed=.1)),('no_tip_loss',dict(tip_loss='none'))]:
        solved,answer,_=target(replace(mid,**changed),.09*.089)
        summary=answer[0]
        fm=summary['thrust_coefficient']**1.5/(np.sqrt(2)*summary['torque_coefficient'])
        sensitivities.append(dict(change=label,collective_deg=solved.collective_deg,cq=summary['torque_coefficient'],fm_equivalent=fm))
    write_csv(output/'sensitivity.csv',list(sensitivities[0]),([row[key] for key in sensitivities[0]] for row in sensitivities))
    legacy=[]
    with (source/'legacy_model_checks.csv').open(encoding='utf-8',newline='') as stream:
        historical=list(csv.DictReader(stream))
    for cts in (.06,.09,.12):
        solved,answer,_=target(replace(rotor,axial_speed=.1),cts*.089)
        summary=answer[0]
        fm=summary['thrust_coefficient']**1.5/(np.sqrt(2)*summary['torque_coefficient'])
        legacy.append(dict(ct_sigma=cts,rdl_cq_at_0_1=summary['torque_coefficient'],rdl_fm_equivalent_at_0_1=fm,
            **{f'{method}_archived_cq':float(min((row for row in historical if row['method']==method),key=lambda row:abs(float(row['ct'])-cts*.089))['cq']) for method in ('bem','ccblade')}))
    write_csv(output/'legacy_comparison.csv',list(legacy[0]),([row[key] for key in legacy[0]] for row in legacy))
    stats={mode:dict(mean_power_error_pct=float(np.mean([r['power_error_pct'] for r in rows if r['model']==mode])),
        max_abs_power_error_pct=max(abs(r['power_error_pct']) for r in rows if r['model']==mode)) for mode in ('uniform','annular')}
    provenance=json.loads((source/'provenance.json').read_text(encoding='utf-8'))
    plot=provenance['plot_calibration']; bound=provenance['marker_center_bound_pt']
    dx=bound/(plot['x1']-plot['x0'])*.14;dy=bound/(plot['y0']-plot['y1'])*.014
    stats.update(solver_version=__version__,points=len(rows),max_target_relative_error=max(r['target_relative_error'] for r in rows),
        grid_relative_change_480_960=changes,vector_marker_bound=dict(ct_sigma=dx,cq_sigma=dy),
        source_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in source.glob('*') if path.is_file()})
    write_json(output/'checks.json',stats)
    plot_results(source,output)
    print(json.dumps(stats,ensure_ascii=True),flush=True)


def plot_results(source,output):
    reference=np.loadtxt(source/'legacy_reference_ct_cq.csv',delimiter=',')
    with (source/'betzina_fig15.csv').open(encoding='utf-8',newline='') as stream:
        markers=list(csv.DictReader(stream))
    digitization={run:np.array([[float(row['ct_sigma']),float(row['cq_sigma'])] for row in markers if int(row['run'])==run]) for run in (33,51)}
    with (output/'comparison.csv').open(encoding='utf-8',newline='') as stream:
        rows=[{key:float(value) if key in ('ct_sigma','cq','power_error_pct') else value for key,value in row.items()} for row in csv.DictReader(stream)]
    bounds=read_case(output/'checks.json')['vector_marker_bound']
    dx,dy=bounds['ct_sigma'],bounds['cq_sigma']
    os.environ.setdefault('MPLCONFIGDIR',str(Path(gettempdir())/'rotordesignlab-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    axes[0].plot(reference[:,0],reference[:,1],'k.',label='Reused public digitization')
    for run,values in digitization.items():
        axes[0].errorbar(values[:,0],values[:,1],xerr=dx,yerr=dy,fmt='o' if run==33 else '^',
                         markersize=4,alpha=.6,label=f'PDF vector markers: Run {run}')
    for mode in ('uniform','annular'):
        selected=[r for r in rows if r['model']==mode]
        x=[r['ct_sigma'] for r in selected]
        color={'uniform':'#1f77b4','annular':'#d62728'}[mode]
        axes[0].plot(x,[r['cq']/.089 for r in selected],'o-',label=mode,color=color)
        axes[1].plot(x,[r['power_error_pct'] for r in selected],'o-',label=mode,color=color)
    axes[0].set(xlabel='CT / sigma',ylabel='CQ / sigma',xlim=(.04,.135),ylim=(.002,.014))
    axes[1].set(xlabel='CT / sigma',ylabel='Same-thrust power error / %')
    axes[1].axhline(0,color='gray',linewidth=.8)
    for axis in axes:axis.grid(alpha=.25);axis.legend(fontsize=8)
    fig.suptitle('XV-15 metal rotor | Mtip = 0.691 | rigid blade, no Reynolds correction')
    fig.savefig(output/'comparison.png',dpi=160);fig.savefig(output/'comparison.svg');plt.close(fig)
    svg=output/'comparison.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=Path('validation/xv15'))
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--plot-only',action='store_true')
    args=parser.parse_args()
    if args.plot_only:plot_results(args.source,args.out)
    else:run(args.source,args.out,args.resume)
