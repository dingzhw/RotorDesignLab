"""Independent checks: force scale m Ω² L, moment scale m Ω² L².

Normalized tolerance 1e-6; near-zero analytical force/moment absolute 1e-8 SI.
Finite-difference acceleration uses a five-point stencil in inertial space.
"""
import unittest
import numpy as np
from scipy.spatial.transform import Rotation

from rotordesignlab.hub_loads import BladeMass, blade_motion, blade_on_hub, flap_inertial_moment


class HubLoadsTest(unittest.TestCase):
    def setUp(self):
        self.psi = np.linspace(0, 2 * np.pi, 36, endpoint=False)
        self.beta = .08 + .03 * np.cos(self.psi) - .02 * np.sin(self.psi)
        self.mass = BladeMass(3., 1.5, 1., 1.)  # uniform 1 m blade

    def motion(self, sign=1, hinge=.07, **kwargs):
        return blade_motion(self.psi, self.beta, .2 * np.sin(self.psi),
                            -1.3 * np.cos(self.psi), 35., sign, hinge, **kwargs)

    def test_mass_moments_need_explicit_mass_and_consistency(self):
        for values in [(0, 1, 1, 1), (1, 2, 1, 1), (1, .5, .6, 1), (1, .7, .3, 1), (np.nan, 1, 1, 1)]:
            with self.assertRaises(ValueError):
                BladeMass(*values)
        BladeMass(2, 1, .5, 1)  # concentrated mass, allowed equality

    def test_inertial_force_and_moment_against_independent_space_differences(self):
        nodes, weights = np.polynomial.legendre.leggauss(8)
        span = (nodes + 1) / 2
        dm = weights * self.mass.mass_kg / 2
        rate = np.array([.4, -.3, .2])
        angular_acc = np.array([.7, -.2, .3])
        hub_acc = np.array([.5, -.8, 1.2])
        beta_dot = .2 * np.sin(self.psi)
        beta_ddot = -1.3 * np.cos(self.psi)
        for sign in (-1, 1):
            for rate_sign in (-1, 1):
                with self.subTest(sign=sign, rate_sign=rate_sign):
                    w = rate_sign * rate
                    motion = self.motion(sign, body_rates=w, hub_acceleration=hub_acc, body_acceleration=angular_acc)
                    def positions(t):
                        psi = self.psi + sign * 35 * t
                        beta = self.beta + beta_dot * t + .5 * beta_ddot * t*t
                        er = np.column_stack((np.cos(psi), np.sin(psi), np.zeros_like(psi)))
                        x = (.07 + np.cos(beta)[:, None] * span)[:, :, None] * er[:, None, :]
                        x[:, :, 2] = np.sin(beta)[:, None] * span
                        return x @ Rotation.from_rotvec(w*t + .5*angular_acc*t*t).as_matrix().T + .5*hub_acc*t*t
                    dt = 3e-5
                    x = positions(0)
                    acceleration = (-positions(2*dt) + 16*positions(dt) - 30*x
                                    + 16*positions(-dt) - positions(-2*dt)) / (12*dt**2)
                    expected_force = np.einsum('nrj,r->nj', acceleration, dm)
                    expected_moment = np.einsum('nrj,r->nj', np.cross(x, acceleration), dm)
                    zeros = np.zeros((len(self.psi), 3))
                    loads = blade_on_hub(motion, self.mass, zeros, zeros)
                    force_scale = self.mass.mass_kg * 35**2 * 1.07
                    moment_scale = force_scale * 1.07
                    self.assertLess(np.max(abs(loads['inertial_force'] - expected_force))/force_scale, 1e-6)
                    self.assertLess(np.max(abs(loads['inertial_moment'] - expected_moment))/moment_scale, 1e-6)

    def test_mass_matrix_and_reference_shift(self):
        zero = np.zeros((len(self.psi), 3))
        base = blade_on_hub(self.motion(), self.mass, zero, zero)
        acceleration = np.array([.4, -.2, .7, .3, -.4, .5])
        moved = blade_on_hub(self.motion(hub_acceleration=acceleration[:3],
                                       body_acceleration=acceleration[3:]), self.mass, zero, zero)
        difference = np.column_stack((moved['force'] - base['force'], moved['moment'] - base['moment']))
        np.testing.assert_allclose(difference, -base['mass_matrix'] @ acceleration, atol=1e-10)
        np.testing.assert_allclose(base['mass_matrix'], base['mass_matrix'].transpose(0, 2, 1), atol=1e-12)
        # Direct mass-point assembly at a shifted point, with a rotated basis.
        rotation = Rotation.from_euler('xyz', [.2, -.4, .6]).as_matrix()
        offset = np.array([.3, -.1, -.5])
        nodes, weights = np.polynomial.legendre.leggauss(8)
        for i in (0, 9, 17):
            positions = (self.motion()['origin'][i] + (nodes[:, None]+1)/2 * self.motion()['span'][i]) @ rotation.T + offset
            expected = np.zeros((6, 6))
            for point, weight in zip(positions, weights * 1.5):
                mapping = np.column_stack((np.eye(3), -np.array([[0,-point[2],point[1]], [point[2],0,-point[0]], [-point[1],point[0],0]])))
                expected += weight * mapping.T @ mapping
            skew = np.array([[0,-offset[2],offset[1]], [offset[2],0,-offset[0]], [-offset[1],offset[0],0]])
            transform = np.block([[rotation, np.zeros((3,3))], [skew @ rotation, rotation]])
            np.testing.assert_allclose(transform @ base['mass_matrix'][i] @ transform.T, expected, atol=1e-12)

    def test_free_hinge_offset_spring_damper_and_fixed_blade(self):
        gravity = np.array([.8, -.3, -9.7])
        beta_dot = .2 * np.sin(self.psi)
        for sign in (-1, 1):
            for hinge, spring, damping in [(0, 0, 0), (.07, 0, 0), (.07, 4, .3)]:
                with self.subTest(sign=sign, hinge=hinge, spring=spring, damping=damping):
                    # Single external normal force at a specified blade station.
                    normal_force = (20 + 3 * np.cos(self.psi))[:, None]
                    base = blade_motion(self.psi, self.beta, beta_dot, np.zeros_like(self.psi),
                                        35., sign, hinge, body_rates=[.1, -.2, .05],
                                        hub_acceleration=[.2, .3, .4], body_acceleration=[.3, -.1, .2])
                    aero_force = normal_force * base['normal']
                    aero_moment = np.cross(base['origin'] + .7 * base['span'], aero_force)
                    restraint = spring * (self.beta - .02) + damping * beta_dot
                    generalized_force = .7 * normal_force[:, 0] + self.mass.first_moment_kg_m * (base['normal'] @ gravity)
                    ddot = (generalized_force - restraint - flap_inertial_moment(base, 1.5, 1.)) / self.mass.second_moment_kg_m2
                    motion = blade_motion(self.psi, self.beta, beta_dot, ddot, 35., sign, hinge,
                                          body_rates=[.1, -.2, .05], hub_acceleration=[.2, .3, .4], body_acceleration=[.3, -.1, .2])
                    loads = blade_on_hub(motion, self.mass, aero_force, aero_moment, gravity=gravity)
                    hinge_moment = loads['moment'] - np.cross(motion['origin'], loads['force'])
                    transmitted = np.einsum('ij,ij->i', hinge_moment, motion['flap_axis'])
                    np.testing.assert_allclose(transmitted, restraint, atol=1e-8)
        # Fixed flat blade: no flap acceleration; transverse aerodynamic moment
        # is transmitted rather than artificially zeroed as if it were free.
        zeros = np.zeros_like(self.psi)
        motion = blade_motion(self.psi, zeros, zeros, zeros, 35., 1, 0)
        force = np.tile([0., 0., 20.], (len(zeros), 1))
        moment = np.cross(.7 * motion['span'], force)
        loads = blade_on_hub(motion, self.mass, force, moment)
        np.testing.assert_allclose(loads['moment'], moment, atol=1e-8)


if __name__ == '__main__':
    unittest.main()
