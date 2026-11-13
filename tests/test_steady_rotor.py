from dataclasses import replace
import unittest
import numpy as np
from rotordesignlab.cases import THREE_BLADE,read_case,read_rotor
from rotordesignlab.rotor import solve
from rotordesignlab.steady_rotor import SteadyRotor,pitt_peters


FIXED=dict(mode='fixed',hinge_offset_m=0,precone_deg=0,max_flap_deg=15)
HINGED=dict(mode='hinged',hinge_offset_m=.04,precone_deg=0,max_flap_deg=15,
            inertia_kg_m2=.75,first_mass_moment_kg_m=1.,spring_nm_rad=0,damper_nms_rad=0)


class SteadyRotorTest(unittest.TestCase):
    def setUp(self):self.rotor,_=read_rotor(read_case(THREE_BLADE),THREE_BLADE.parent)

    def test_axial_momentum_and_uniform_limit(self):
        for speed in (0,25):
            r=replace(self.rotor,axial_speed=speed);reference=solve(r)[0]
            state,data,diag=SteadyRotor(r,FIXED).solve(np.deg2rad([r.collective_deg,0,0]),[0,0,speed])
            self.assertAlmostEqual(data['force'][2],reference['thrust_n'],places=6)
            self.assertAlmostEqual(data['power'],reference['power_w'],places=5)
            self.assertLess(diag['internal_max_residual'],1e-8)
        residual,_=pitt_peters(np.array([.05,0,0]),np.zeros(3),.005,np.zeros(2))
        np.testing.assert_allclose(residual,0,atol=1e-10)

    def test_flap_balance_and_zero_speed_continuity(self):
        model=SteadyRotor(self.rotor,HINGED)
        controls=np.deg2rad([13,0,0]);state,data,diag=model.solve(controls,[0,0,0])
        self.assertGreater(state[3],0);np.testing.assert_allclose(state[[1,2,4,5]],0,atol=1e-9)
        for speed in (1e-7,.001):
            nearby,loads,d=model.solve(controls,[speed,0,0],initial=state)
            self.assertLess(abs(loads['force'][2]/data['force'][2]-1),1e-6)
        opposite=SteadyRotor(self.rotor,HINGED,-1)
        state1,data1,_=model.solve(np.deg2rad([13,1,0]),[0,0,0])
        state2,data2,_=opposite.solve(np.deg2rad([13,1,0]),[0,0,0])
        self.assertAlmostEqual(state1[4],state2[4],places=7)
        self.assertAlmostEqual(state1[5],-state2[5],places=7)
        self.assertGreater(abs(state1[5]),1e-3)

    def test_forward_grid_and_force_asymmetry(self):
        answers=[]
        for nr,na in ((60,24),(120,48),(240,96)):
            r=replace(self.rotor,stations=nr)
            state,data,diag=SteadyRotor(r,HINGED,azimuth_stations=na).solve(np.deg2rad([13,0,0]),[25,0,0])
            self.assertLess(diag['internal_max_residual'],1e-6)
            self.assertGreater(abs(state[4])+abs(state[5]),.001)
            answers.append([data['force'][2],data['torque'],data['power']])
        self.assertLess(np.max(abs(np.array(answers[-1])/answers[-2]-1)),.002)
