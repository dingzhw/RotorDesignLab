"""Public component-data aircraft; frozen control assumptions remain explicit."""
from pathlib import Path
import re,shutil
import numpy as np
from scipy.io import loadmat
from rotordesignlab.cases import read_case,write_json

ROOT=Path(__file__).resolve().parents[1]


def build():
    out=ROOT/'examples/public-helicopter';out.mkdir(exist_ok=True)
    source=ROOT/'examples/trim'
    for p in source.glob('*.csv'):shutil.copyfile(p,out/p.name)
    synthetic=read_case(source/'synthetic.json');synthetic['mass_properties'].update(inertia_cg_kg_m2=np.diag([30,45,60]).tolist(),
        provenance='Synthetic rigid-body inertia estimate; not measured, symmetric tensor in body axes')
    write_json(out/'synthetic.json',synthetic)
    a=read_case(source/'uh60-public.json');main,tail=a['rotors']
    a['id']='uh60-public-components';a['name']='UH-60 公开部件模型（含显式假设）'
    a['mass_properties'].update(mass_kg=16400*.45359237,cg_m=[-2.4*.0254,0,.0254],
        inertia_cg_kg_m2=(np.array([[5629,0,-1670],[0,40000,0],[-1670,0,37200]])*(14.59390294*.3048**2)).tolist(),
        provenance='NASA TM-85890 Table 1 mass/CG/inertia; Ixz tensor entry=-product. Coordinates relative to FS358/WL248.2.')
    main['polar_json']='../../validation/aero-upgrade/gh-full.json'
    main['description']='公开主桨几何及原模型BT/UT分段全攻角气动表；未引入斜流修正'
    tail.pop('polar_csv');tail['polar_json']='../../validation/aero-upgrade/naca0012-re.json'
    inertia=3.1*14.59390294*.3048**2;R=tail['radius_m']
    tail['flight']['flapping'].update(mode='hinged',precone_deg=0,delta3_deg=float(np.rad2deg(np.arctan(.7002075))),
        inertia_kg_m2=inertia,first_mass_moment_kg_m=1.5*inertia/R*(1-.2**2)/(1-.2**3),spring_nm_rad=0,damper_nms_rad=0)
    tail['flight']['provenance']='Public IbTR=3.10 slug ft2 and tan(delta3)=0.7002075; first mass moment from uniform blade 0.2R..R (estimate). Independent hinged blades, no teeter constraint or VT blockage.'
    raw=loadmat(ROOT/'data/H60fuselage.mat')
    def t(angles,keys):return dict(angle_deg=raw[angles].ravel().tolist(),**{k:(raw[src].ravel()*.3048**power).tolist() for k,src,power in keys})
    fus=a['trim']['fuselage'];fus.pop('alpha_table');fus.pop('beta_table')
    fus.update(position_m=[(358-345.5)*.0254,0,(248.2-234)*.0254],area_m2=1,length_m=1,wake_fraction=0,
        wind_tables=dict(alpha=t('FUSEAOA',[('cd_m2','FUSEDA',2),('cl_m2','FUSELA',2),('cm_m3','FUSEMA',3)]),
                         beta=t('FUSEBETA',[('cy_m2','FUSEYB',2),('cl_m2','FUSELB',2),('roll_m3','FUSERB',3),('yaw_m3','FUSENB',3)]),
                         abs_beta=t('FUSEABETA',[('cd_m2','FUSEDB',2),('cm_m3','FUSEMB',3)])),
        provenance='Public H60fuselage.mat dimensional wind coefficients, ft2/ft3 converted SI; original GenHel wind/body signs. Fuselage downwash disabled; residual download separately estimated.')
    text=(ROOT/'src/H60_constants.jl').read_text(encoding='utf-8');angles=[*range(-90,-39,10),*range(-30,31,5),*range(40,91,10)]
    for i,s in enumerate(a['trim']['surfaces'],1):
        def array(key):return [float(v) for v in re.search(rf'{key}\[{i},:\]=\[(.*?)\]',text,re.S)[1].replace('\n',' ').split(',')]
        s['polar']=dict(angle_deg=angles,cl=array('CLTAIL'),cd=array('CDTAIL'))
        s['area_m2']=(45 if i==1 else 32.3)*.3048**2
        s['position_m']=[(358-(700 if i==1 else 695))*.0254,0,(248.2-(244 if i==1 else 273))*.0254]
        s.update(pressure_ratio=.4 if i==1 else .651,wake_fraction=1.8 if i==1 else 0,tail_wake_fraction=0 if i==1 else 1.)
        s['reverse_flow_symmetry']=True
        s['provenance']='H60_constants geometry/CLTAIL/CDTAIL within +/-90deg; outside uses explicit symmetric reversed-chord estimate (CL sign reversed, CD held at mirrored alpha), no test data. TM-85890 pressure/wake factors. HT schedule freezes collective reference at 50%, ignores q/acceleration feedback. No control-system replication.'
        if i==1:
            speeds=np.arange(0,81,2.);kt=speeds*3600/1852
            incidence=np.clip(42-np.clip(kt-30,0,50)*(.003286*20+.67)-.1119*np.clip(kt-80,0,67),-8,39)
            s['incidence_schedule']=dict(speed_m_s=speeds.tolist(),angle_deg=incidence.tolist())
    a['description']='Public tables + blade-element tail with delta3; explicit approximate wake and frozen-control assumptions. Low-frequency open-loop model estimate.'
    write_json(out/'uh60-public.json',a)
    for name in ('synthetic','uh60-public'):
        case=read_case(source/f'{name}-case.json');write_json(out/f'{name}-case.json',case)


if __name__=='__main__':build()
