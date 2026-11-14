"""Publish a compact, reproducible numeric record without changing reference data."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from rotordesignlab.cases import read_case,read_rotor,run_case,write_json
from rotordesignlab.aircraft import AERO_KEYS
from rotordesignlab.rotor import solve
from rotordesignlab.isolated import setup,evaluate

ROOT=Path(__file__).resolve().parents[1]
records={'scope':'software and model consistency, not new flight validation','checks':{}}
source=ROOT/'validation/caradonna-tung/hover.json';case=read_case(source)
case.update(inflow_model='uniform',tip_loss='none')
rotor,_=read_rotor(case,source.parent)
selected=dict(thrust_axis_body=[0,0,-1],rotation_sign=1)
spatial_case=dict(flow_body_m_s=[0,0,0],flapping_model='fixed',azimuth_stations=36)
model,state,loads,diag=evaluate(rotor,selected,setup(spatial_case,selected,rotor))
old=solve(rotor)[0]
ct=float(loads['force'][2]/model.scale)
ratios={k:float(v/old[k]-1) for k,v in [('thrust_n',loads['force'][2]),('torque_nm',loads['torque']),('power_w',loads['power'])]}
assert max(map(abs,ratios.values()))<1e-4,ratios
# Axial momentum uses the projected disk, while the existing Pitt-Peters kernel
# normalizes by nominal R. The zero-precone limit must agree to roundoff.
zero=replace(rotor,precone_deg=0.)
_,_,zero_loads,_=evaluate(zero,selected,setup(spatial_case,selected,zero))
zero_old=solve(zero)[0]
zero_difference=abs(zero_loads['force'][2]/zero_old['thrust_n']-1)
assert zero_difference<1e-9,zero_difference
records['checks']['caradonna_tung_uniform_limit']=dict(case='NASA TM-81232, 1250 rpm / 8 deg / 0.5 deg precone',
    reference_ct=.0046,computed_ct=ct,ct_error_percent=100*(ct/.0046-1),relative_difference_from_existing_uniform=ratios,
    zero_precone_thrust_relative_difference=zero_difference,
    note='Pitt-Peters uses nominal disk area; old axial momentum uses projected area with precone. Existing thrust bias retained; no fitting or accuracy improvement claimed.')
answers=[]
for nr,na in ((60,24),(120,48),(240,96)):
    cfg=read_case(ROOT/'examples/three-blade.json');cfg['radial_stations']=nr
    r,_=read_rotor(cfg,ROOT/'examples')
    c=dict(flow_body_m_s=[-15.,-4.,3.],azimuth_stations=na)
    m,x,d,diagnostic=evaluate(r,selected,setup(c,selected,r))
    answers.append(dict(radial=nr,azimuth=na,thrust_n=float(d['force'][2]),torque_nm=d['torque'],power_w=d['power']))
differences={k:abs(answers[-1][k]/answers[-2][k]-1)*100 for k in ('thrust_n','torque_nm','power_w')}
assert max(differences.values())<=.2,differences
records['checks']['synthetic_xyz_grid']=dict(flow_body_m_s=[-15.,-4.,3.],levels=answers,last_change_percent=differences)
with TemporaryDirectory() as temporary,patch('rotordesignlab.isolated.plot_elements'):
    for index,(role,flow) in enumerate([('main',[-20.,0.,0.]),('tail',[-10.,-2.,3.])]):
        c=dict(schema_version=2,model='spatial_rotor',aircraft_json=str(ROOT/'examples/public-helicopter/uh60-public.json'),
               rotor_id=role,flow_body_m_s=flow,flapping_model='aircraft',radial_stations=80,azimuth_stations=36)
        result=run_case(c,ROOT,Path(temporary)/str(index))
        assert result['status']=='converged',result
        records['checks']['uh60_'+role]=dict(flow_body_m_s=flow,summary=result['summary'],
            force_body_n=result['installation']['force_body_n'],diagnostics=result['diagnostics'])
path=ROOT/'validation/isolated-3d/checks.json';path.parent.mkdir(parents=True,exist_ok=True)
write_json(path,records)
print(path)
print('C-T uniform limit: CT =',ct,'bias % =',records['checks']['caradonna_tung_uniform_limit']['ct_error_percent'])
print('Last grid change %:',differences)
