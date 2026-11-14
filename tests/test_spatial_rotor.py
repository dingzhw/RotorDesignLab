from copy import deepcopy
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import numpy as np

from rotordesignlab.cases import read_case,run_case,write_json
from rotordesignlab.aircraft import snapshot_aircraft

ROOT=Path(__file__).resolve().parents[1]


class SpatialRotorTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name);self.count=0
        source=ROOT/'examples/synthetic-aircraft.json'
        snapshot_aircraft(read_case(source),source.parent,self.root)
        self.case=dict(schema_version=2,model='spatial_rotor',aircraft_json='aircraft.json',rotor_id='main',
                       flow_body_m_s=[0,0,0],rpm=1700.,collective_deg=13.,radial_stations=80,
                       azimuth_stations=36,flapping_model='fixed')
        self.plot=patch('rotordesignlab.isolated.plot_elements');self.plot.start()

    def tearDown(self):self.plot.stop();self.temp.cleanup()

    def run_point(self,case=None):
        self.count+=1;out=self.root/str(self.count)
        return run_case(case or self.case,self.root,out),out

    def test_axial_limit_and_rotation(self):
        for axial in (0.,5.):
            spatial,_=self.run_point(dict(self.case,flow_body_m_s=[0,0,axial]))
            old=dict(self.case,model='aircraft_rotor',axial_speed_m_s=axial)
            for k in ('flow_body_m_s','azimuth_stations','flapping_model'):old.pop(k)
            reference,_=self.run_point(old)
            self.assertEqual(spatial['status'],'converged',spatial)
            for key in ('thrust_n','torque_nm','power_w'):
                self.assertAlmostEqual(spatial['summary'][key]/reference['summary'][key],1.,places=9)
            np.testing.assert_allclose(spatial['installation']['force_body_n'][:2],0,atol=1e-9)
        a=read_case(self.root/'aircraft.json');a['rotors'][0]['rotation_sign']=-1;write_json(self.root/'aircraft.json',a)
        reverse,_=self.run_point(dict(self.case,flow_body_m_s=[0,0,5.]))
        self.assertAlmostEqual(reverse['summary']['thrust_n'],spatial['summary']['thrust_n'],places=6)
        self.assertAlmostEqual(reverse['installation']['moment_hub_body_nm'][2],-spatial['installation']['moment_hub_body_nm'][2],places=7)

    def test_three_components_covariance_and_load_integrals(self):
        case=dict(self.case,flow_body_m_s=[-15.,-4.,3.])
        result,out=self.run_point(case);self.assertEqual(result['status'],'converged',result)
        R=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        rotated,_=self.run_point(dict(case,flow_body_m_s=(R@case['flow_body_m_s']).tolist()))
        self.assertEqual(rotated['status'],'converged',rotated)
        np.testing.assert_allclose(rotated['installation']['force_body_n'],R@result['installation']['force_body_n'],atol=1e-7)
        np.testing.assert_allclose(rotated['installation']['moment_hub_body_nm'],R@result['installation']['moment_hub_body_nm'],atol=1e-7)
        self.assertGreater(abs(result['installation']['force_body_n'][0]),1)
        self.assertGreater(abs(result['installation']['force_body_n'][1]),.1)
        with (out/'radial_loads.csv').open() as stream:rows=list(csv.DictReader(stream))
        self.assertAlmostEqual(sum(float(r['dthrust_n']) for r in rows),result['summary']['thrust_n'],places=7)
        self.assertAlmostEqual(sum(float(r['dtorque_nm']) for r in rows),result['summary']['torque_nm'],places=7)
        s=result['summary'];self.assertAlmostEqual(s['power_w'],s['rpm']*np.pi/30*s['torque_nm'],places=7)
        a=read_case(self.root/'aircraft.json');rotor=a['rotors'][0]
        arm=np.array(rotor['position_m'])-a['mass_properties']['cg_m']
        np.testing.assert_allclose(result['installation']['moment_cg_body_nm'],
            np.array(result['installation']['moment_hub_body_nm'])+np.cross(arm,result['installation']['force_body_n']))
        replay=run_case(read_case(out/'case.json'),out,self.root/'moved-replay')
        self.assertEqual(replay['summary'],s)
        # Rotate the complete installation 90 degrees about body X (tail-rotor axis).
        R=np.array([[1,0,0],[0,0,-1],[0,1,0]])
        rotor['thrust_axis_body']=(R@rotor['thrust_axis_body']).tolist()
        rotor['position_m']=(R@rotor['position_m']).tolist()
        a['mass_properties']['cg_m']=(R@a['mass_properties']['cg_m']).tolist()
        write_json(self.root/'aircraft.json',a)
        tail,_=self.run_point(dict(case,flow_body_m_s=(R@case['flow_body_m_s']).tolist()))
        self.assertEqual(tail['status'],'converged',tail)
        np.testing.assert_allclose(tail['installation']['force_body_n'],R@result['installation']['force_body_n'],atol=1e-7)
        np.testing.assert_allclose(tail['installation']['moment_cg_body_nm'],R@result['installation']['moment_cg_body_nm'],atol=1e-7)

    def test_inverse_collective_and_rpm(self):
        case=dict(self.case,flow_body_m_s=[-12.,3.,2.])
        forward,_=self.run_point(case);self.assertEqual(forward['status'],'converged',forward)
        for variable in ('collective_deg','rpm'):
            inverse,out=self.run_point(dict(case,target=dict(thrust_n=forward['summary']['thrust_n'],solve_for=variable)))
            self.assertEqual(inverse['status'],'converged',inverse)
            self.assertAlmostEqual(inverse['summary'][variable],case[variable],places=6)
            replay=run_case(read_case(out/'solved-case.json'),out,self.root/('solved-'+variable))
            self.assertEqual(replay['summary'],inverse['summary'])

    def test_domain_and_unknown_fields(self):
        for changes,text in [({'flow_body_m_s':[1,2]},'三个'),({'flow_body_m_s':[0,0,-2]},'下降'),
            ({'flow_body_m_s':[-70,0,0]},'推进比'),({'axial_speed_m_s':3},'轴流专用'),
            ({'flow_body_m_s':[-45,0,1]},'翼型表'),
            ({'flapping_model':'aircraft'},'缺少挥舞'),({'target':dict(thrust_n=1e8,solve_for='collective_deg')},'目标拉力')]:
            with self.subTest(changes=changes):
                result,_=self.run_point(dict(self.case,**changes))
                self.assertEqual(result['status'],'failed',result);self.assertIn(text,result['error'])

    def test_grid_and_zero_flow_continuity(self):
        base,_=self.run_point()
        nearby,_=self.run_point(dict(self.case,flow_body_m_s=[-1e-6,1e-6,0]))
        self.assertAlmostEqual(base['summary']['thrust_n'],nearby['summary']['thrust_n'],places=7)
        answers=[]
        for nr,na in ((60,24),(120,48),(240,96)):
            result,_=self.run_point(dict(self.case,flow_body_m_s=[-15.,-4.,3.],radial_stations=nr,azimuth_stations=na))
            self.assertEqual(result['status'],'converged',result)
            answers.append([result['summary'][key] for key in ('thrust_n','torque_nm','power_w')])
        self.assertLess(np.max(abs(np.array(answers[-1])/answers[-2]-1)),.002)

    def test_aircraft_flapping_and_flow_batch(self):
        from rotordesignlab.batch import run_batch
        source=ROOT/'examples/public-helicopter/synthetic.json'
        snapshot_aircraft(read_case(source),source.parent,self.root)
        case=dict(self.case,flow_body_m_s=[-12.,3.,2.],flapping_model='aircraft')
        result,_=self.run_point(case);self.assertEqual(result['status'],'converged',result)
        self.assertGreater(abs(result['summary']['flap_cos_deg'])+abs(result['summary']['flap_sin_deg']),.1)
        write_json(self.root/'source.json',case)
        spec=dict(schema_version=1,kind='rotor_sweep',case_json='source.json',axes={'flow_x_m_s':[0.,-10.,-15.]})
        answer=run_batch(spec,self.root,self.root/'batch')
        self.assertEqual(answer['summary']['converged'],3,answer)
        # Changing X must preserve simultaneous Y/Z components in every snapshot.
        for i,x in enumerate(spec['axes']['flow_x_m_s']):
            actual=read_case(self.root/'batch'/f'case-{i:04d}'/'case.json')
            self.assertEqual(actual['flow_body_m_s'],[x,3.,2.])


if __name__=='__main__':unittest.main()
