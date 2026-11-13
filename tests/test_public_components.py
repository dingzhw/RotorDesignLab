from copy import deepcopy
from pathlib import Path
import unittest
import numpy as np
from rotordesignlab.cases import read_rotor,read_case,THREE_BLADE
from rotordesignlab.aircraft import read_aircraft,require_analysis
from rotordesignlab.airframe import airframe_loads
from rotordesignlab.steady_rotor import SteadyRotor

ROOT=Path(__file__).resolve().parents[1]


class PublicComponentsTest(unittest.TestCase):
    def test_public_input_and_fuselage_reference(self):
        a=read_aircraft(ROOT/'examples/public-helicopter/uh60-public.json');require_analysis(a,'trim')
        ref=np.loadtxt(ROOT/'validation/public-components/julia-fuselage.csv',delimiter=',',skiprows=1)
        for row in ref:
            item=airframe_loads(a,row[:3],1.225,np.zeros(3))['fuselage']
            np.testing.assert_allclose(np.r_[item['force_body_n'],item['moment_cg_body_nm']],row[3:],atol=1e-8,rtol=1e-10)

    def test_delta3_negative_feedback_and_local_rate(self):
        rotor,_=read_rotor(read_case(THREE_BLADE),THREE_BLADE.parent)
        cfg=dict(mode='hinged',hinge_offset_m=.04,precone_deg=0,max_flap_deg=15,
                 inertia_kg_m2=.75,first_mass_moment_kg_m=1.,spring_nm_rad=0,damper_nms_rad=0)
        states=[]
        for delta in [0,35]:
            model=SteadyRotor(rotor,dict(cfg,delta3_deg=delta));s,d,_=model.solve(np.deg2rad([13,0,0]),[0,0,0])
            states.append(s)
            pitch=np.deg2rad(d['pitch_deg'])-model.kernel.twist
            np.testing.assert_allclose(pitch,np.deg2rad(13)-np.tan(np.deg2rad(delta))*d['beta'][:,None]+np.zeros_like(pitch),atol=1e-12)
        self.assertLess(states[1][3],states[0][3])
        a=read_aircraft(ROOT/'examples/public-helicopter/synthetic.json');a['trim']['surfaces']=[]
        v=np.array([20,0,2]);rates=np.array([.1,.2,-.1]);fus=a['trim']['fuselage']
        local=v+np.cross(rates,np.asarray(fus['position_m'])-a['mass_properties']['cg_m'])
        original=airframe_loads(a,v,1.225,np.zeros(3),body_rates=rates)
        equivalent=airframe_loads(a,local,1.225,np.zeros(3))
        self.assertEqual(original,equivalent)

    def test_surface_schedule_and_data_checks(self):
        a=read_aircraft(ROOT/'examples/public-helicopter/uh60-public.json');b=deepcopy(a)
        b['trim']['surfaces'][0]['incidence_schedule']['speed_m_s'][1]=0
        with self.assertRaisesRegex(ValueError,'递增'):require_analysis(b,'trim')
        with self.assertRaisesRegex(ValueError,'越界'):airframe_loads(a,[90,0,0],1.225,np.zeros(3),True)
        # Reverse-chord estimate is opt-in, and retains a diagnostic.
        a['trim']['surfaces']=a['trim']['surfaces'][1:]
        r=airframe_loads(a,[-1,1,0],1.225,np.zeros(3),True)
        self.assertTrue(r['vertical_tail']['reverse_flow_estimate'])
        a['trim']['surfaces'][0]['reverse_flow_symmetry']=False
        with self.assertRaisesRegex(ValueError,'数据域'):airframe_loads(a,[-1,1,0],1.225,np.zeros(3),True)
