from copy import deepcopy
from dataclasses import replace
import json
from math import pi
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from rotordesignlab.airfoils import AirfoilGrid
from rotordesignlab.axial import prandtl_tip, solve_axial
from rotordesignlab.cases import EXAMPLES, read_case, read_rotor, run_case, write_json
from rotordesignlab.inverse import solve_target
from rotordesignlab.rotor import solve

VALIDATION=Path(__file__).resolve().parents[1]/'validation/xv15'


class AxialTest(unittest.TestCase):
    def test_source_airfoil_nodes_and_domain(self):
        grid=AirfoilGrid.read(VALIDATION/'airfoils.json')
        self.assertAlmostEqual(grid.coefficients(.2,0,0)[0],.26)
        self.assertAlmostEqual(grid.coefficients(.2,0,0)[1],.014)
        self.assertAlmostEqual(grid.coefficients(.55,4,.5)[0],.514)
        for section in grid.sections:
            for index,key in enumerate(('cl','cd')):
                table=section[key]
                a=np.array(table['alpha_deg'])[:,None];m=np.array(table['mach'])[None,:]
                value=grid.coefficients(section['r_over_R'],a,m)[index]
                np.testing.assert_allclose(value,table['values'],rtol=0,atol=1e-12)
        with self.assertRaisesRegex(ValueError,'domain'):
            grid.coefficients(.2,0,.8,strict=True)
        broken=deepcopy(grid.data);broken['sections'][0]['cd']['values'][0][0]=-1
        with self.assertRaises(ValueError):AirfoilGrid(broken)

    def test_interpolation_in_three_independent_coordinates(self):
        def expected(r,a,m):return r+.2*a+2*m+.3*a*m
        sections=[]
        for r in (.2,.8):
            table=dict(alpha_deg=[-5,5],mach=[0,.5],values=[[expected(r,a,m) for m in (0,.5)] for a in (-5,5)])
            sections.append(dict(r_over_R=r,cl=table,cd=dict(alpha_deg=[-5,5],mach=[0,.5],values=[[.01,.01],[.01,.01]])))
        grid=AirfoilGrid(dict(schema_version=1,kind='spanwise_airfoil',span_boundary='hold_endpoint',sections=sections))
        self.assertAlmostEqual(grid.coefficients(.4,1,.2,strict=True)[0],expected(.4,1,.2))

    def test_uniform_solver_matches_existing_baseline(self):
        original,_=read_rotor(read_case(EXAMPLES/'three-blade.json'),EXAMPLES)
        for speed in (0,25):
            rotor=replace(original,axial_speed=speed)
            legacy=solve(rotor)[0];new=solve_axial(rotor)[0]
            for key in ('thrust_n','torque_nm','power_w','induced_speed_m_s'):
                self.assertAlmostEqual(new[key]/legacy[key],1,places=9)

    def test_prandtl_and_annular_balance(self):
        self.assertAlmostEqual(prandtl_tip(3,.5,pi/2),2/pi*np.arccos(np.exp(-1.5)))
        self.assertAlmostEqual(prandtl_tip(3,.5,0),1)
        rotor,_=read_rotor(read_case(VALIDATION/'hover.json'),VALIDATION)
        summary,columns,rows=solve(rotor);data=dict(zip(columns,np.array(list(rows)).T))
        cone=np.cos(np.deg2rad(rotor.precone_deg));vi=data['induced_speed_m_s']
        expected=4*pi*rotor.density*data['r_m']*data['dr_m']*cone**2*data['tip_loss_factor']*vi**2
        np.testing.assert_allclose(data['dthrust_n'],expected,rtol=0,atol=1e-6)
        self.assertAlmostEqual(sum(data['dthrust_n']),summary['thrust_n'],places=7)
        self.assertAlmostEqual(sum(data['dtorque_nm']),summary['torque_nm'],places=7)
        self.assertAlmostEqual(summary['power_w'],rotor.omega*summary['torque_nm'],places=7)

    def test_tabulated_target_and_portable_aircraft(self):
        case=read_case(VALIDATION/'hover.json');rotor,_=read_rotor(case,VALIDATION)
        thrust=solve(rotor)[0]['thrust_n']
        solved,answer,diagnostic=solve_target(rotor,dict(thrust_n=thrust,solve_for='collective_deg',bounds=[8,12]),
                                            dict(collective_deg=[2,20],rpm=[400,650]))
        self.assertLess(diagnostic['relative_thrust_error'],1e-8)
        self.assertAlmostEqual(solved.collective_deg,10,places=6)
        with TemporaryDirectory() as temporary:
            base=Path(temporary)
            for name in ('synthetic-aircraft.json','synthetic-geometry.csv'):
                shutil.copyfile(EXAMPLES/name,base/name)
            shutil.copyfile(VALIDATION/'airfoils.json',base/'airfoils.json')
            aircraft=read_case(base/'synthetic-aircraft.json')
            selected=aircraft['rotors'][0];selected.pop('polar_csv')
            selected.update(polar_json='airfoils.json',precone_deg=1.5,inflow_model='annular',tip_loss='prandtl')
            write_json(base/'synthetic-aircraft.json',aircraft)
            first=run_case(read_case(EXAMPLES/'engineering-rotor.json'),base,base/'first')
            self.assertEqual(first['status'],'converged',first)
            replay=run_case(read_case(base/'first/case.json'),base/'first',base/'replay')
            self.assertEqual(first['summary'],replay['summary'])
            self.assertTrue((base/'first/rotor-0-polar.json').is_file())


if __name__=='__main__':unittest.main()
