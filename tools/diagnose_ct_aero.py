"""Separate C-T input effects from wake-model error; never calibrate a production correction."""
from pathlib import Path
from dataclasses import replace
import argparse
import numpy as np
from scipy.optimize import brentq
from rotordesignlab.airfoils import AirfoilGrid
from rotordesignlab.cases import read_case,read_rotor,write_csv,write_json
from rotordesignlab.rotor import solve
from tools.prepare_caradonna import FREE,make_airfoil

ROOT=Path(__file__).resolve().parents[1]


def diagnose(out):
    out.mkdir(parents=True,exist_ok=False);base=ROOT/'validation/caradonna-tung'
    rotor,_=read_rotor(read_case(base/'hover.json'),base)
    ref=np.genfromtxt(base/'reference.csv',delimiter=',',names=True);x=ref['r_over_R'];target=ref['cl_reported']
    legacy=AirfoilGrid.read(ROOT/'validation/aero-upgrade/naca0012-re.json')
    variants={'baseline_annular':rotor,'baseline_uniform':replace(rotor,inflow_model='uniform',tip_loss='none'),
              'legacy_local_Re_Mach_held':replace(rotor,airfoil_grid=legacy),
              'legacy_fixed_Re2e6_Mach_held':replace(rotor,airfoil_grid=AirfoilGrid(dict(schema_version=1,kind='spanwise_airfoil',
                   span_boundary='hold_endpoint',sections=[dict(r_over_R=0,**legacy.data['sections'][0]['reynolds_slices'][4])])))}
    # Finite-wing lift slope is a diagnostic limiting approximation, NOT rotor wake theory.
    finite=[(a,cl/(1+2*np.pi/(np.pi*6)),cd) for a,cl,cd in FREE]
    variants['finite_wing_AR6_diagnostic_only']=replace(rotor,airfoil_grid=AirfoilGrid(make_airfoil(finite)),tip_loss='none')
    rows=[];radials={}
    for name,r in variants.items():
        s,h,z=solve(r);z=np.array(list(z));radials[name]={k:z[:,i] for i,k in enumerate(h)}
        y=np.interp(x*r.radius,radials[name]['r_m'],radials[name]['section_thrust_coefficient'])
        rows.append(dict(model=name,ct=s['thrust_coefficient'],ct_error_percent=(s['thrust_coefficient']/.0046-1)*100,
            radial_mape_percent=float(np.mean(abs(y/target-1))*100),power_w=s['power_w']))
    d=radials['baseline_annular'];inference=[]
    for span,observed in zip(x,target):
        radius=span*rotor.radius;tangent=rotor.omega*radius*np.cos(np.deg2rad(rotor.precone_deg));chord=.1905
        def load(vi):
            axial=vi*np.cos(np.deg2rad(rotor.precone_deg));phi=np.arctan2(axial,tangent);speed=np.hypot(tangent,axial)
            cl,cd=rotor.airfoil_grid.coefficients(span,8-np.rad2deg(phi),speed/rotor.speed_of_sound,
                reynolds=rotor.density*speed*chord/rotor.dynamic_viscosity,strict=True)
            return (1+(axial/tangent)**2)*(cl*np.cos(phi)-cd*np.sin(phi))*np.cos(np.deg2rad(rotor.precone_deg))
        inferred=brentq(lambda v:load(v)-observed,0,20)
        predicted=float(np.interp(radius,d['r_m'],d['induced_speed_m_s']))
        inference.append(dict(r_over_R=span,observed_sectional_cl=observed,annular_induced_m_s=predicted,
            load_inferred_induced_m_s=inferred,inferred_over_annular=inferred/predicted))
    for name,data in [('variants',rows),('inflow-diagnostic',inference)]:
        keys=list(data[0]);write_csv(out/f'{name}.csv',keys,([r[k] for k in keys] for r in data))
    write_json(out/'findings.json',dict(reference_ct=.0046,engineering_accuracy_qualified=False,
        input_review='Original Table 17 and Figure 6 rechecked: 8deg,1250rpm,Mtip=.439,CT=.00460; no transcription discrepancy found.',
        re_scope='Six legacy Re slices cover the rotor; small-alpha CL slope is Re-independent in this database. Experimental pedigree/Mach effects not established.',
        finite_wing='AR6 e=1 slope formula is a diagnostic only, no Prandtl multiplier; finite wing is not a validated rotor wake replacement.',
        inference='Inverted measured sectional load using same airfoil; diagnostic is conditioned on assumed airfoil, not measured induced velocity.',variants=rows))
    print(rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);diagnose(p.parse_args().out)
