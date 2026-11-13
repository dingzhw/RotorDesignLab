from dataclasses import replace
import unittest
import numpy as np
from rotordesignlab.azimuth import AzimuthRotor,rotor_basis
from rotordesignlab.cases import THREE_BLADE,read_case,read_rotor
from rotordesignlab.rotor import solve


class AzimuthTest(unittest.TestCase):
    def setUp(self):self.rotor,_=read_rotor(read_case(THREE_BLADE),THREE_BLADE.parent)

    def test_axial_limit_and_reverse_rotation(self):
        for velocity in (0.,25.):
            r=replace(self.rotor,axial_speed=velocity);s=solve(r)[0]
            for sign in (-1,1):
                a=AzimuthRotor(r,36,sign)
                out=a.elements(np.deg2rad([r.collective_deg,0,0]),[s['inflow_mean'],0,0],[0,0,0],[0,0,velocity])
                np.testing.assert_allclose(out['force'],[0,0,s['thrust_n']],atol=1e-9)
                self.assertAlmostEqual(out['power'],s['power_w'],places=7)
                self.assertAlmostEqual(out['moment'][2],-sign*s['torque_nm'],places=8)

    def test_cyclic_flap_kinematics_and_basis(self):
        a=AzimuthRotor(self.rotor,36,-1)
        beta=np.deg2rad([2,1,-.5]);theta=np.deg2rad([10,2,3])
        out=a.elements(theta,[.05,0,0],beta,[20,0,2],strict=False)
        self.assertAlmostEqual(out['beta_dot'][0],-self.rotor.omega*beta[2])
        self.assertAlmostEqual(out['pitch_deg'][0,0]-out['pitch_deg'][18,0],4)
        R=rotor_basis([0,1,0],[1,0,0]);np.testing.assert_allclose(R.T@R,np.eye(3));self.assertAlmostEqual(np.linalg.det(R),1)
        # Work of aerodynamic force against rotation agrees with shaft torque.
        vrot=self.rotor.omega*np.linalg.norm(out['position'][:,:,:2],axis=2)[:,:,None]*a.et[:,None,:]
        work=-self.rotor.blades*np.mean(np.sum(out['element_force']*vrot,axis=(1,2)))
        self.assertAlmostEqual(work,out['power'],places=7)

    def test_four_quadrants_and_domain_rejection(self):
        a=AzimuthRotor(self.rotor,36)
        with self.assertRaisesRegex(ValueError,'四象限'):
            a.elements([.1,0,0],[.05,0,0],[0,0,0],[70,0,0])
        alpha=np.arange(-180,181,2);rad=np.deg2rad(alpha)
        full=replace(self.rotor,polar=np.column_stack((alpha,np.sin(2*rad),.02+2*np.sin(rad)**2)))
        out=AzimuthRotor(full,36).elements([.1,0,0],[.05,0,0],[0,0,0],[70,0,0])
        self.assertGreater(out['reverse_flow_fraction'],0)
        self.assertTrue(np.isfinite(out['force']).all())
