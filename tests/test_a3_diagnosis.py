"""Independent checks on the diagnostic intervention and reference integrator."""
import unittest
import numpy as np
from rotordesignlab.perturbation import Perturbation
from tools.diagnose_a3_amplitude import FrozenSegments, integrate


class DiagnosisTests(unittest.TestCase):
    def test_frozen_segments_match_trim_and_change_only_off_trim(self):
        polar = np.array([[-2., -.2, .04], [0., 0., .01], [2., .4, .05]])
        alpha = np.array([[-1., 1.]])
        frozen = FrozenSegments(polar, alpha)
        cl, cd = frozen.coefficients(None, alpha, None)
        np.testing.assert_allclose(cl, [[-.1, .2]])
        np.testing.assert_allclose(cd, [[.025, .03]])
        crossed, _ = frozen.coefficients(None, np.array([[1., -1.]]), None)
        np.testing.assert_allclose(crossed, [[.1, -.2]])
        self.assertNotAlmostEqual(crossed[0, 0], np.interp(1., polar[:, 0], polar[:, 1]))
        with self.assertRaises(ValueError):
            frozen.coefficients(None, np.array([[3., 1.]]), None)

    def test_dop853_matches_analytic_constant_input_solution(self):
        class Linear:
            state = np.zeros(21)
            controls = np.zeros(4)
            state_scale = np.linspace(.1, 2., 21)

            def rhs(self, state, controls):
                return -state + controls[2]*np.arange(1, 22)

        b = np.zeros((21, 4))
        b[:, 2] = np.arange(1, 22)
        data, _ = integrate(Linear(), -np.eye(21), b, .02,
                            waveform=Perturbation(kind='step', amplitude_deg=.02))
        expected = (1-np.exp(-data[:, 0]))[:, None]*np.deg2rad(.02)*np.arange(1, 22)
        np.testing.assert_allclose(data[:, 1:22], expected, atol=1e-13, rtol=1e-10)
        np.testing.assert_allclose(data[:, 22:], expected, atol=1e-13, rtol=1e-10)


if __name__ == '__main__':
    unittest.main()
