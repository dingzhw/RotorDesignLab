import unittest
from copy import deepcopy
import numpy as np
from rotordesignlab import rotor_trial as t, module_workspace as store
from rotordesignlab.module_manager_ui import new_scheme


class TrialTests(unittest.TestCase):
    def test_signed_axes_rotations_and_gravity(self):
        for angles in ([0, 0, 0], [20, -35, 70], [0, 90, 0], [90, 0, 0]):
            matrix = t.basis(angles)
            np.testing.assert_allclose(matrix.T @ matrix, np.eye(3), atol=1e-14)
            self.assertAlmostEqual(np.linalg.det(matrix), 1.)
            np.testing.assert_allclose(np.cross(matrix[:, 0], matrix[:, 1]), matrix[:, 2], atol=1e-14)
            for axis in np.eye(3):
                for sign in (-1, 1):
                    motion = axis*sign*10
                    flow = t.motion_to_flow(motion, angles)
                    np.testing.assert_allclose(t.flow_to_motion(flow, angles), motion, atol=1e-13)
                    # Force/moment vectors must use the same proper rotation.
                    np.testing.assert_allclose(np.cross(matrix @ [1, 2, 3], matrix @ [4, 5, 6]), matrix @ np.cross([1, 2, 3], [4, 5, 6]), atol=1e-13)
            np.testing.assert_allclose(matrix @ t.gravity(angles, 9.80665), [0, 0, 9.80665], atol=1e-13)
        np.testing.assert_allclose(t.motion_to_flow([10, 3, 2], [0, 0, 0]), [10, -3, 2])

    def test_old_new_packages_and_mismatch(self):
        old = store.template(next(iter(store.TEMPLATES)))
        self.assertEqual(store.unpack(store.pack(old)), old)
        new = new_scheme(next(iter(store.TEMPLATES)))
        self.assertEqual(store.unpack(store.pack(new)), new)
        new['trial']['angles_deg'] = [0., 90., 0.]
        with self.assertRaises(ValueError):
            store.pack(new)
        new['case']['gravity_rotor_m_s2'] = t.gravity([0., 90., 0.], 9.80665).tolist()
        self.assertEqual(store.unpack(store.pack(new)), new)

    def test_precone_branches_and_same_input_results(self):
        original = store.template(next(iter(store.TEMPLATES)))
        original['case'].update(radial_stations=24, azimuth_stations=12)
        original['module']['rotor']['precone_deg'] = 4.
        original['module']['flapping']['precone_deg'] = 2.
        original['case']['flapping_model'] = 'fixed'
        self.assertEqual(t.effective_flap(original)[1]['precone_deg'], 4.)
        for sign in (-1, 1):
            draft = deepcopy(original)
            draft['module']['rotor']['rotation_sign'] = sign
            draft['case'].update(cyclic_cos_deg=.4, cyclic_sin_deg=-.3, flow_rotor_m_s=[3., 2., -1.])
            first = store.execute(draft)['answer']
            self.assertEqual(first['status'], 'converged')
            self.assertAlmostEqual(first['summary']['flap_coning_deg'], 4., places=8)
            motion = t.flow_to_motion(draft['case']['flow_rotor_m_s'], [20., 30., 40.])
            draft['case']['flow_rotor_m_s'] = t.motion_to_flow(motion, [20., 30., 40.]).tolist()
            second = store.execute(draft)['answer']
            for name in ('force_rotor_n', 'moment_hub_rotor_nm'):
                np.testing.assert_allclose(second[name], first[name], rtol=1e-6, atol=1e-7)
        for stiffness in (0., 1000.):
            draft = deepcopy(original)
            draft['case']['flapping_model'] = 'module'
            draft['module']['flapping'].update(mode='hinged', spring_nm_rad=stiffness, precone_deg=0.)
            first = store.execute(draft)['answer']
            draft['module']['flapping']['precone_deg'] = 3.
            second = store.execute(draft)['answer']
            self.assertEqual(first['status'], 'converged')
            self.assertEqual(second['status'], 'converged')
            if stiffness == 0.:
                np.testing.assert_allclose(first['force_rotor_n'], second['force_rotor_n'], rtol=1e-6, atol=1e-7)
                self.assertAlmostEqual(first['summary']['flap_coning_deg'], second['summary']['flap_coning_deg'], delta=1e-8)
            else:
                self.assertGreater(abs(first['summary']['flap_coning_deg']-second['summary']['flap_coning_deg']), 1e-5)


if __name__ == '__main__':
    unittest.main()
