from copy import deepcopy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from rotordesignlab.cases import read_case, run_case, write_json
from rotordesignlab.hover import G

ROOT=Path(__file__).resolve().parents[1]


class HoverTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        shutil.copytree(ROOT/'examples/hover',self.base/'inputs')
        self.case=read_case(self.base/'inputs/synthetic-case.json')
        self.count=0

    def run_point(self, **overrides):
        self.count+=1
        out=self.base/str(self.count)
        return run_case(dict(self.case,**overrides),self.base/'inputs',out),out

    def test_balance_power_and_replay(self):
        result,out=self.run_point()
        self.assertEqual(result['status'],'converged',result)
        s=result['summary']
        self.assertAlmostEqual(s['main_thrust_n'],200*G/.97,places=7)
        self.assertAlmostEqual(s['tail_thrust_n']*1.7,s['main_torque_nm'],places=7)
        expected=s['main_power_w']/.96+s['tail_power_w']/.93+700
        self.assertAlmostEqual(s['required_power_w'],expected,places=7)
        for role in ('main','tail'):
            self.assertAlmostEqual(s[role+'_power_w'],s[role+'_torque_nm']*s[role+'_rpm']*np.pi/30)
        self.assertGreater(result['residual_force_body_n'][1],0)
        self.assertLess(s['max_scaled_balance_residual'],1e-4)
        moved=self.base/'moved';shutil.copytree(out,moved)
        replay=run_case(read_case(moved/'case.json'),moved,self.base/'replay')
        self.assertEqual(s,replay['summary'])
        import hashlib
        for name,sha in read_case(moved/'input-sha256.json').items():
            self.assertEqual(hashlib.sha256((moved/name).read_bytes()).hexdigest(),sha)

    def test_limits_failures_duration_and_altitude(self):
        aircraft=read_case(self.base/'inputs/synthetic.json')
        aircraft['powerplant']['continuous_power_w']=[30000]*4
        aircraft['powerplant']['short_time_power_w']=[60000]*4
        write_json(self.base/'inputs/synthetic.json',aircraft)
        long,_=self.run_point();short,_=self.run_point(requested_duration_s=60)
        self.assertEqual(long['status'],'converged');self.assertFalse(long['feasible'])
        self.assertTrue(short['feasible']);self.assertTrue(short['short_time_rating_applicable'])
        failed,out=self.run_point(mass_kg=900)
        self.assertEqual(failed['status'],'failed');self.assertIn('diagnostics',failed)
        self.assertEqual(read_case(out/'case.json')['aircraft_json'],'aircraft.json')
        for override in (dict(altitude_m=-1),dict(analysis='trim'),dict(main_rpm=4000),dict(main_radius_m=2.0)):
            bad,_=self.run_point(**override);self.assertEqual(bad['status'],'failed')
        aircraft['powerplant']['altitude_m']=[0,100,200,300]
        write_json(self.base/'inputs/synthetic.json',aircraft)
        bad,_=self.run_point(altitude_m=1000);self.assertIn('不外推',bad['error'])

    def test_installation_sign_and_public_cant(self):
        aircraft=read_case(self.base/'inputs/synthetic.json')
        aircraft['rotors'][0]['rotation_sign']=-1
        write_json(self.base/'inputs/synthetic.json',aircraft)
        wrong,_=self.run_point();self.assertEqual(wrong['status'],'failed')
        aircraft['rotors'][1]['thrust_axis_body']=[0,-1,0]
        write_json(self.base/'inputs/synthetic.json',aircraft)
        reversed_,_=self.run_point();self.assertEqual(reversed_['status'],'converged')
        self.assertLess(reversed_['summary']['tail_side_force_n'],0)
        self.case=read_case(self.base/'inputs/uh60-public-case.json')
        public,_=self.run_point();self.assertEqual(public['status'],'converged',public)
        c=public['components'];f=np.array([0,0,public['summary']['weight_n']+public['summary']['download_n']]);m=np.zeros(3)
        a=read_case(self.base/'inputs/uh60-public.json')
        for rotor in a['rotors']:
            role=rotor['role'];axis=np.asarray(rotor['thrust_axis_body'])
            force=c[role]['summary']['thrust_n']*axis
            f+=force;m+=np.cross(rotor['position_m'],force)-rotor['rotation_sign']*c[role]['summary']['torque_nm']*axis
        np.testing.assert_allclose(f,public['residual_force_body_n'],atol=1e-8)
        np.testing.assert_allclose(m,public['residual_moment_body_nm'],atol=1e-8)

    def test_grid_and_radius_rule(self):
        results=[]
        for n in (120,240,480):
            r,_=self.run_point(radial_stations=n);self.assertEqual(r['status'],'converged');results.append(r['summary'])
        for key in ('main_thrust_n','main_torque_nm','tail_thrust_n','tail_torque_nm','required_power_w'):
            self.assertLess(abs(results[-1][key]/results[-2][key]-1),.002)
        r,out=self.run_point(main_radius_m=1.2,main_rpm=1600)
        self.assertEqual(r['status'],'converged',r)
        np.testing.assert_array_equal(np.loadtxt(out/'rotor-0-geometry.csv',delimiter=',',skiprows=1),
                                      np.loadtxt(self.base/'inputs/synthetic-geometry.csv',delimiter=',',skiprows=1))
