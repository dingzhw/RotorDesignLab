from copy import deepcopy
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from rotordesignlab.aircraft import read_aircraft,require_analysis
from rotordesignlab.airframe import body_to_ned,flight_velocity,airframe_loads
from rotordesignlab.cases import read_case,run_case,write_json

ROOT=Path(__file__).resolve().parents[1]


class TrimTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        shutil.copytree(ROOT/'examples/trim',self.base/'inputs');self.case=read_case(self.base/'inputs/synthetic-case.json')
        self.count=0

    def run_point(self,**overrides):
        self.count+=1;out=self.base/str(self.count)
        r=run_case(dict(self.case,**overrides),self.base/'inputs',out);return r,out

    def test_hover_forward_climb_and_force_accounting(self):
        for speed,climb in ((0,0),(20,0),(0,2)):
            result,out=self.run_point(speed_m_s=speed,climb_m_s=climb)
            self.assertEqual(result['status'],'converged',result)
            s=result['summary'];self.assertLess(s['max_scaled_residual'],1e-4);self.assertLess(s['max_internal_residual'],1e-6)
            R=body_to_ned(*np.deg2rad([s['roll_deg'],s['pitch_deg']]))
            force=R.T@np.array([0,0,200*9.80665]);moment=np.zeros(3)
            for c in result['components'].values():force+=c['force_body_n'];moment+=c['moment_cg_body_nm']
            np.testing.assert_allclose(force,result['residual_force_body_n'],atol=1e-8)
            np.testing.assert_allclose(moment,result['residual_moment_body_nm'],atol=1e-8)
            earth=R@result['velocity_body_m_s'];self.assertAlmostEqual(earth[2],-climb,places=8)
            self.assertAlmostEqual(np.linalg.norm(earth[:2]),speed,places=8)
            if speed:self.assertAlmostEqual(result['velocity_body_m_s'][1],0)
            self.assertAlmostEqual(s['required_power_w'],s['main_power_w']/.96+s['tail_power_w']/.93+700)

    def test_replay_limits_and_unavailable_fields(self):
        r,out=self.run_point();self.assertEqual(r['status'],'converged',r)
        moved=self.base/'moved';shutil.copytree(out,moved)
        replay=run_case(read_case(moved/'case.json'),moved,self.base/'replay')
        self.assertEqual(r['summary'],replay['summary'])
        a=read_aircraft(self.base/'inputs/synthetic.json');a['powerplant']['continuous_power_w']=[1]*4
        write_json(self.base/'inputs/synthetic.json',a)
        poor,_=self.run_point();self.assertEqual(poor['status'],'converged');self.assertFalse(poor['feasible'])
        a['rotors'][0]['limits']['collective_deg']=[2,3];a['rotors'][0]['defaults']['collective_deg']=2.5
        write_json(self.base/'inputs/synthetic.json',a)
        saturated,_=self.run_point();self.assertEqual(saturated['status'],'failed');self.assertEqual(saturated['failure_kind'],'control_limited')
        old=read_aircraft(ROOT/'examples/hover/synthetic.json')
        with self.assertRaisesRegex(ValueError,'缺少'):require_analysis(old,'trim')

    def test_domains_and_surface_translation(self):
        r,_=self.run_point(climb_m_s=-1);self.assertEqual(r['status'],'failed')
        r,_=self.run_point(speed_m_s=70);self.assertEqual(r['status'],'failed')
        a=read_aircraft(self.base/'inputs/synthetic.json');before=airframe_loads(a,[20,0,2],1.225,np.zeros(3),True)
        a['mass_properties']['cg_m'][0]+=.1;after=airframe_loads(a,[20,0,2],1.225,np.zeros(3),True)
        for key in before:
            np.testing.assert_allclose(after[key]['force_body_n'],before[key]['force_body_n'])
            expected=np.asarray(before[key]['moment_cg_body_nm'])+np.cross([-.1,0,0],before[key]['force_body_n'])
            np.testing.assert_allclose(after[key]['moment_cg_body_nm'],expected)
        a['trim']['surfaces'][0]['id']='main'
        with self.assertRaisesRegex(ValueError,'部件名称'):require_analysis(a,'trim')

    def test_combined_cg_tail_arm_override_replay(self):
        r,out=self.run_point(speed_m_s=20,cg_x_m=.05,tail_arm_m=2.)
        self.assertEqual(r['status'],'converged',r)
        saved=read_case(out/'aircraft.json');tail=next(x for x in saved['rotors'] if x['role']=='tail')
        self.assertAlmostEqual(saved['mass_properties']['cg_m'][0]-tail['position_m'][0],2.)
        replay=run_case(read_case(out/'case.json'),out,self.base/'combined-replay')
        self.assertEqual(r['summary'],replay['summary'])
