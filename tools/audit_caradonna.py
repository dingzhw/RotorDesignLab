"""Independent scalar C-T implementation and raw-table audit.

The reference function does not call Rotor, AirfoilGrid, axial.py or their
quadrature/root helpers. SciPy RGI + scalar Brent contrast the product's
bilinear implementation + vector bisection. This is software intercomparison.
"""
import argparse
import hashlib
import json
from math import acos, atan2, cos, exp, hypot, pi, radians, sin, sqrt
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import brentq


def independent(source):
    case=json.loads((source/'hover.json').read_text(encoding='utf-8'))
    geometry=np.loadtxt(source/'geometry.csv',delimiter=',',skiprows=1)
    grid=json.loads((source/'airfoils.json').read_text(encoding='utf-8'))
    assert len(grid['sections'])==1
    tables={}
    for key in ('cl','cd'):
        table=grid['sections'][0][key]
        tables[key]=(np.array(table['alpha_deg']),np.array(table['mach']),
                     RegularGridInterpolator((table['alpha_deg'],table['mach']),np.array(table['values'])))
    radius=case['radius_m'];omega=case['rpm']*pi/30;rho=case['density_kg_m3']
    cone=cos(radians(case['precone_deg']));blades=case['blade_count'];n=case['radial_stations']
    dr=radius*(1-geometry[0,0])/n
    reference_twist=float(np.interp(case['pitch_reference_r_over_R'],geometry[:,0],geometry[:,2]))
    rows=[]
    for index in range(n):
        r=radius*geometry[0,0]+(index+.5)*dr;arm=r*cone;ut=omega*arm
        chord=float(np.interp(r/radius,geometry[:,0],geometry[:,1]))
        pitch=radians(case['collective_deg']+np.interp(r/radius,geometry[:,0],geometry[:,2])-reference_twist)

        def element(vi, strict=False):
            up=(case['axial_speed_m_s']+vi)*cone;phi=atan2(up,ut)
            alpha=(pitch-phi)*180/pi;mach=hypot(ut,up)/case['speed_of_sound_m_s']
            coeff=[]
            for key in ('cl','cd'):
                aa,mm,interp=tables[key]
                if strict:assert aa[0]<=alpha<=aa[-1] and mm[0]<=mach<=mm[-1]
                coeff.append(float(interp([[np.clip(alpha,aa[0],aa[-1]),np.clip(mach,mm[0],mm[-1])]])[0]))
            cl,cd=coeff;force=.5*rho*(ut*ut+up*up)*chord*dr*blades
            thrust=force*(cl*cos(phi)-cd*sin(phi))*cone
            torque=force*(cl*sin(phi)+cd*cos(phi))*arm
            tip=2/pi*acos(exp(-blades/2*(radius-r)/(r*max(abs(sin(phi)),1e-12))))
            momentum=4*pi*rho*arm*(dr*cone)*tip*vi*(case['axial_speed_m_s']+vi)
            return thrust-momentum,thrust,torque,alpha,mach,cl,cd,tip

        vi=brentq(lambda v:element(v)[0],0,omega*radius,xtol=1e-11)
        _,thrust,torque,alpha,mach,cl,cd,tip=element(vi,True)
        normal=thrust/(.5*rho*(omega*r)**2*chord*dr*blades)
        rows.append([r,vi,thrust,torque,alpha,mach,cl,cd,tip,normal])
    return np.asarray(rows),case


def run(source,out):
    out.mkdir(parents=True,exist_ok=False)
    rows,case=independent(source)
    # Independently reconstruct generated nodes from measured CSV and the declared PG model.
    raw=np.loadtxt(source/'ladson-free.csv',delimiter=',',skiprows=1)
    grid=json.loads((source/'airfoils.json').read_text(encoding='utf-8'))['sections'][0]
    node_error={}
    for key,column in [('cl',1),('cd',2)]:
        table=grid[key];mm=np.array(table['mach']);values=np.array(table['values'])
        data=np.vstack((raw,np.array([[-a,-cl,cd] for a,cl,cd in raw if a>-raw[0,0]])))
        data=data[np.argsort(data[:,0])]
        np.testing.assert_array_equal(data[:,0],table['alpha_deg'])
        expected=data[:,column,None]*np.ones((1,len(mm)))
        if key=='cl':expected*=np.sqrt(1-.15**2)/np.sqrt(1-mm**2)
        node_error[key]=float(np.max(abs(values-expected)))
        assert node_error[key]<1e-12

    from rotordesignlab.cases import read_rotor,write_json,write_csv
    from rotordesignlab.rotor import solve
    product,_=read_rotor(case,source);summary,columns,iterator=solve(product)
    actual=dict(zip(columns,np.array(list(iterator)).T))
    compare={'r_m':0,'induced_speed_m_s':1,'dthrust_n':2,'dtorque_nm':3,
             'alpha_deg':4,'mach':5,'cl':6,'cd':7,'tip_loss_factor':8}
    errors={key:float(np.max(abs(actual[key]-rows[:,column]))) for key,column in compare.items()}
    # Global sums and nominal-rotation-pressure load coefficients use independent formulas.
    thrust=float(rows[:,2].sum());torque=float(rows[:,3].sum());omega=case['rpm']*pi/30
    ct=thrust/(case['density_kg_m3']*pi*case['radius_m']**2*(omega*case['radius_m'])**2)
    reference=np.genfromtxt(source/'reference.csv',delimiter=',',names=True)
    predicted=np.interp(reference['r_over_R'],rows[:,0]/case['radius_m'],rows[:,9])
    relative={'thrust':abs(thrust/summary['thrust_n']-1),'torque':abs(torque/summary['torque_nm']-1)}
    assert max(relative.values())<1e-8,relative
    assert errors['induced_speed_m_s']<1e-7 and errors['cl']<1e-8,errors
    record=dict(status='independent_implementation_agrees',reference_type='software/model intercomparison, not new experiment',
        stations=case['radial_stations'],source_node_max_abs_error=node_error,max_abs_element_difference=errors,
        relative_total_difference=relative,independent_ct=ct,ct_error_pct=(ct/.0046-1)*100,
        radial_mape_pct=float(np.mean(abs(predicted/reference['cl_reported']-1))*100),
        independent_thrust_n=thrust,independent_torque_nm=torque,independent_power_w=omega*torque,
        conclusion='No implementation discrepancy at this case. Fixed-collective physical discrepancy remains.',
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()})
    write_json(out/'audit.json',record)
    write_csv(out/'independent-radial.csv',['r_m','induced_m_s','dthrust_n','dtorque_nm','alpha_deg','mach','cl','cd','tip_loss','nominal_q_normal_coefficient'],rows)
    write_csv(out/'stations.csv',['r_over_R','reference','independent','error_pct'],
              zip(reference['r_over_R'],reference['cl_reported'],predicted,(predicted/reference['cl_reported']-1)*100))
    print(json.dumps(record,ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=Path('validation/caradonna-tung'))
    args=parser.parse_args();run(args.source,args.out)
