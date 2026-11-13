"""Public geometry + explicitly estimated airframe/flap inputs for trim demos."""
from pathlib import Path
from copy import deepcopy
import shutil
import numpy as np
from scipy.io import loadmat
from rotordesignlab.cases import read_case,write_json


def build(out):
    base=Path(__file__).resolve().parents[1]/'examples/hover'
    out.mkdir(parents=True,exist_ok=True)
    for source in base.glob('*.csv'):shutil.copyfile(source,out/source.name)
    angles=list(range(-180,181,5));a=np.deg2rad(angles)
    for name in ('synthetic','uh60-public'):
        aircraft=read_case(base/f'{name}.json');large=name.startswith('uh60');main,tail=aircraft['rotors']
        if large:
            raw=loadmat(base.parents[1]/'data/GHRotorData.mat')
            table={key:dict(alpha_deg=list(range(-32,33,2)),mach=np.linspace(0,1,11).tolist(),
                           values=(raw[source].reshape(33,11,order='F')+offset).tolist())
                   for key,source,offset in [('cl','CLR0BT',0),('cd','CDR0BT',.002)]}
            write_json(out/'uh60-main-airfoils.json',dict(schema_version=1,kind='spanwise_airfoil',
                span_boundary='hold_endpoint',provenance='Public J-GenHel GHRotorData.mat CLR0BT/CDR0BT, Fortran column order; CD+0.002 as GenHel. Bounded alpha only; no skew-angle correction or Reynolds axis.',
                sections=[dict(r_over_R=0,**table)]))
            main.pop('polar_csv');main['polar_json']='uh60-main-airfoils.json'
            main['description']='公开主桨几何及原模型攻角/Mach气动表（±32°）；无斜流修正'
        main['defaults']['radial_stations']=80;tail['defaults']['radial_stations']=80
        main['defaults']['collective_deg']=8 if large else 13
        main['flight']=dict(x_reference_body=[1,0,0],cyclic_cos_deg=[-15,15],cyclic_sin_deg=[-15,15],
            flapping=dict(mode='hinged',hinge_offset_m=1.25*.3048 if large else .04,
                          precone_deg=0,max_flap_deg=15,inertia_kg_m2=1512.6*14.59390294*.3048**2 if large else 1.2,
                          first_mass_moment_kg_m=86.7*14.59390294*.3048 if large else 1.5,
                          spring_nm_rad=0,damper_nms_rad=0),
            provenance='UH-60 H60_constants IBETA/MBETA/HOFFSET converted SI; control/flap limits estimated' if large else 'All flap mass/hinge/limits synthetic')
        tail['flight']=dict(x_reference_body=[1,0,0],cyclic_cos_deg=[-1,1],cyclic_sin_deg=[-1,1],
            flapping=dict(mode='fixed',hinge_offset_m=0,precone_deg=0,max_flap_deg=15),
            provenance='Fixed rigid tail blade assumption; no cyclic, delta3 or teeter dynamics in this template')
        fus=dict(position_m=[0,0,0],area_m2=6 if large else .45,length_m=8 if large else 2,
            alpha_table=dict(angle_deg=angles,cx=(-.6*np.cos(a)*abs(np.cos(a))).tolist(),
                             cz=(-1.1*np.sin(a)*abs(np.sin(a))).tolist(),cm=(-.02*np.sin(2*a)).tolist()),
            beta_table=dict(angle_deg=angles,cy=(-.8*np.sin(a)).tolist(),cl=(0*a).tolist(),cn=(.02*np.sin(a)).tolist()),
            wake_fraction=0,provenance='Engineering estimate: projected drag and small moments; NOT measured UH-60 fuselage tables. Download separately applied.')
        surfaces=[]
        for role,normal,area,wake in [('horizontal_tail',[0,0,-1],4.18 if large else .16,.15),
                                       ('vertical_tail',[0,1,0],2.0 if large else .12,0)]:
            surfaces.append(dict(id=role,position_m=[-7 if large else -1.5,0,-.2],chord_axis_body=[1,0,0],
                normal_axis_body=normal,area_m2=area,incidence_deg=0,
                polar=dict(angle_deg=angles,cl=(1.2*np.tanh(4.5/2.4*np.sin(2*a))).tolist(),cd=(.015+1.8*np.sin(a)**2).tolist()),
                wake_fraction=wake,provenance='Engineering geometry/polar/wake estimate; smooth full-angle lift/drag; not flight-test calibrated'))
        aircraft['trim']=dict(roll_deg=[-20,20],pitch_deg=[-25,25],fuselage=fus,surfaces=surfaces,
            provenance='Demonstration steady airframe; estimated passive tails, fixed incidence and explicit wake fractions; no schedule/blockage correction')
        aircraft['name']+=' · 六分量配平';aircraft['description']='公开/合成旋翼 + 显式工程机身尾翼；完整稳态平衡，精度待验证。'
        write_json(out/f'{name}.json',aircraft)
        write_json(out/f'{name}-case.json',dict(schema_version=3,model='helicopter',analysis='trim',aircraft_json=f'{name}.json',
            altitude_m=0,speed_m_s=0,climb_m_s=0,requested_duration_s=600,azimuth_stations=36))


if __name__=='__main__':build(Path(__file__).resolve().parents[1]/'examples/trim')
