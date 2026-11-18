"""Ensure longer observation windows cannot turn failed numerical checks green."""
import unittest
import numpy as np
from tools.verify_a3_long_response import compare_histories


class LongResponseTests(unittest.TestCase):
    def setUp(self):
        class Plant:
            state = np.zeros(2)
            state_names = ['body', 'rotor']
            state_scale = np.array([10., .1])
        self.plant = Plant()
        time = np.array([0., 1., 2.])
        self.fine = np.column_stack([time, [0., .1, .2], [0., .001, .002],
                                     [0., .09, .18], [0., .0009, .0018]])

    def test_amplitude_and_step_failures_stay_separate(self):
        half = self.fine.copy()
        half[:, 1:] *= .5
        result = compare_histories(self.fine.copy(), self.fine, half, self.plant)
        self.assertTrue(result['step_passed'])
        self.assertFalse(result['amplitude_passed'])
        self.assertAlmostEqual(result['amplitude_halving_error_ratio'], .5)
        self.assertEqual(result['ratio_limit'], .35)
        self.assertEqual(result['step_limit'], .01)

    def test_step_peak_uses_all_states_and_never_subtracts_drift(self):
        coarse = self.fine.copy()
        coarse[2, 2] += .00003
        half = self.fine.copy()
        half[:, 1:3] = half[:, 3:]+.25*(self.fine[:, 1:3]-self.fine[:, 3:])
        result = compare_histories(coarse, self.fine, half, self.plant)
        self.assertFalse(result['step_passed'])
        self.assertAlmostEqual(result['max_step_halving_relative_change'], .015)
        self.assertEqual(result['step_peak_state'], 'rotor')
        self.assertTrue(result['amplitude_passed'])
        self.assertAlmostEqual(result['amplitude_halving_error_ratio'], .25)


if __name__ == '__main__':
    unittest.main()
