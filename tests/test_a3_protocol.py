"""Guard diagnostic input ownership, signed gearing and response accounting."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from rotordesignlab import designs
from rotordesignlab.mass_partition import Partition, skew
from rotordesignlab.model_scope import open_loop_restriction
from tools.verify_a3_aircraft import candidate, compare_reference, response_check, REFERENCE


class A3ProtocolTests(unittest.TestCase):
    def test_alternative_inertia_is_explicit_and_source_is_unchanged(self):
        original = designs.from_template('UH-60 公开部件模型（含工程估计）')
        before = deepcopy(original)
        incompatible = candidate(original, 'uh60')
        with self.assertRaisesRegex(ValueError, '惯量'):
            Partition(incompatible['aircraft'])
        alternative = candidate(original, 'uh60', inertia_hypothesis='source_as_core')
        partition = Partition(alternative['aircraft'])
        np.testing.assert_allclose(partition.inertia, original['aircraft']['mass_properties']['inertia_cg_kg_m2'],
                                   atol=1e-8, rtol=1e-10)
        self.assertEqual(original, before)
        self.assertIn('alternative hypothesis', alternative['aircraft']['mass_properties']['provenance'])
        restriction = open_loop_restriction(alternative['aircraft'])
        self.assertFalse(restriction['engineering_use_allowed'])
        self.assertIn('幅值检查未通过', restriction['note'])

    def test_signed_control_and_complete_rate_kinematics(self):
        a = np.zeros((9, 9))
        a[:3, 3:6] = skew(np.array([20., 1., .3]))
        b = np.zeros((9, 4))
        b[5, 3] = -2.
        details = dict(frozen_A=a.tolist(), quasi_A=a.tolist(), frozen_B=b.tolist(), quasi_B=b.tolist(),
                       velocity=[20., 1., .3])
        rows = compare_reference(details, 0., 'analytic')
        self.assertEqual(len(rows), 120)
        for row in rows:
            if row[3] in ('X', 'Y', 'Z') and row[4] in ('p', 'q', 'r'):
                self.assertAlmostEqual(row[6], 0.)
            if row[3:5] == ['N_prime', 'DP']:
                self.assertAlmostEqual(row[6], -2*np.deg2rad(.39*.67*100/9.3))
        source = json.loads(REFERENCE.read_text(encoding='utf-8'))
        self.assertEqual(np.asarray([c['values'] for c in source['cases']]).shape, (2, 6, 10))

    def test_21_state_exact_linear_response_and_input_exports(self):
        class Linear:
            state = np.zeros(21)
            controls = np.zeros(4)
            state_scale = np.ones(21)

            def rhs(self, state, controls):
                return -state+controls[2]*np.arange(1, 22)

        b = np.zeros((21, 4))
        b[:, 2] = np.arange(1, 22)
        with TemporaryDirectory() as directory:
            result = response_check(Linear(), -np.eye(21), b, Path(directory), 2, .1)
            self.assertTrue(result['step_passed'])
            self.assertTrue(result['amplitude_passed'])
            self.assertLess(max(result['scaled_nonlinear_linear_errors']), 1e-12)
            self.assertEqual(len(list(Path(directory).glob('input-*.csv'))), 3)


if __name__ == '__main__':
    unittest.main()
