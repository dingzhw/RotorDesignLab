"""Waveform integration, legacy semantics and explicit download policy."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import numpy as np

from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.cases import run_case, read_case
from rotordesignlab.download import settings, load
from rotordesignlab.dynamics import step_response, ResponseDomainError
from rotordesignlab.perturbation import Perturbation, from_case
from rotordesignlab.trim import TrimSystem

ROOT = Path(__file__).resolve().parents[1]


class Integrator:
    state = np.zeros(15)
    controls = np.zeros(4)

    def rhs(self, state, controls):
        derivative = np.zeros(15)
        derivative[0] = controls[0]
        return derivative


class InputPolicyTests(unittest.TestCase):
    def test_analytical_wave_integrals_and_off_grid_breaks(self):
        a = np.zeros((15, 15))
        b = np.zeros((15, 4))
        b[0, 0] = 1
        for kind in ('step', 'pulse', 'doublet'):
            wave = Perturbation(kind, 1., .023, .077)
            history = step_response(Integrator(), a, b, 0, 1., .3, .01, perturbation=wave)
            for event in wave.breakpoints():
                self.assertTrue(np.any(abs(history[:, 0] - event) < 1e-12))
            angle = np.deg2rad(1.)
            expected = angle * {'step': .3 - .023, 'pulse': .077 / 2, 'doublet': 0.}[kind]
            self.assertAlmostEqual(history[-1, 1], expected, delta=2e-8)
            np.testing.assert_allclose(history[:, 1:16], history[:, 16:], atol=1e-14)
        step = from_case(dict(amplitude_deg=.05, duration_s=.1))
        self.assertEqual((step.kind, step.start_s), ('step', 0.))
        self.assertEqual(step.value_deg(0), .05)
        doublet = Perturbation('doublet', .05, .2, .5)
        self.assertEqual([doublet.value_deg(t) for t in (0, .2, .7, 1.2, 2)], [0, .05, -.05, 0, 0])

    def test_input_validation_and_partial_history(self):
        for wave in (Perturbation('bad'), Perturbation('pulse', start_s=-1),
                     Perturbation('doublet', duration_s=.6), Perturbation('pulse', start_s=float('nan'))):
            with self.assertRaises(ValueError):
                wave.validate(1.)

        class Limited(Integrator):
            def rhs(self, state, controls):
                if state[0] > .0004:
                    raise ValueError('test limit')
                return super().rhs(state, controls)

        b = np.zeros((15, 4))
        b[0, 0] = 1
        with self.assertRaises(ResponseDomainError) as error:
            step_response(Limited(), np.zeros((15, 15)), b, 0, 1., .3, .01,
                          perturbation=Perturbation('doublet', 1., .023, .077))
        self.assertTrue(np.all(error.exception.history[:, 1] <= .0004))
        self.assertGreater(len(error.exception.history), 1)

        class ImmediatelyLimited(Integrator):
            def rhs(self, state, controls):
                raise ValueError('initial input outside control limits')

        with self.assertRaises(ResponseDomainError) as error:
            step_response(ImmediatelyLimited(), np.zeros((15, 15)), b, 0, 1., .1, .01)
        self.assertEqual(error.exception.history.shape, (0, 31))

    def test_download_default_legacy_and_analytical_derivative(self):
        source = ROOT / 'examples/public-helicopter'
        aircraft = read_aircraft(source / 'synthetic.json')
        new = deepcopy(aircraft)
        new['trim']['download_policy'] = 'none'
        self.assertEqual(settings(aircraft)['strategy'], 'legacy_fraction')
        self.assertEqual(settings(new)['effective_fraction'], 0.)
        self.assertEqual(settings(new, 'hover_budget')['effective_fraction'], .03)
        case = dict(read_case(source / 'synthetic-case.json'), radial_stations=24, azimuth_stations=24)
        legacy = TrimSystem(aircraft, source, case)
        revised = TrimSystem(new, source, case)
        x = legacy.initial()
        h = 1e-5
        differences, thrusts = [], []
        for sign in (-1, 1):
            varied = x.copy()
            varied[0] += sign * h
            _, old = legacy.loads(varied, np.zeros(3))
            _, fresh = revised.loads(varied, np.zeros(3))
            differences.append(old['force'] - fresh['force'])
            thrusts.append(old['components']['main']['thrust_n'])
        expected = -.03 * (thrusts[1] - thrusts[0]) / (2 * h) * legacy.bases['main'][:, 2]
        np.testing.assert_allclose((differences[1] - differences[0]) / (2 * h), expected, rtol=1e-8, atol=1e-6)
        for velocity in (-1e-6, 0., 1e-6):
            _, data = revised.loads(x, np.array([velocity, 0., 0.]))
            self.assertEqual(data['components']['download']['magnitude_n'], 0.)
            _, data = legacy.loads(x, np.array([velocity, 0., 0.]))
            self.assertAlmostEqual(data['components']['download']['magnitude_n'] /
                                   data['components']['main']['thrust_n'], .03)
        self.assertEqual(load(new, 1000., [0, 0, -1])['force_body_n'], [0., 0., 0.])

    def test_old_response_snapshot_preserves_step_and_download(self):
        with TemporaryDirectory() as directory:
            source = ROOT / 'examples/open-loop'
            case = read_case(source / 'uh60-response.json')
            case.update(duration_s=.05, time_step_s=.005, radial_stations=24, azimuth_stations=24)
            out = Path(directory) / 'response'
            result = run_case(case, source, out)
            self.assertEqual(result['status'], 'converged', result)
            self.assertEqual(result['perturbation']['type'], 'step')
            self.assertEqual(result['download_model']['strategy'], 'legacy_fraction')
            inputs = np.loadtxt(out / 'input.csv', delimiter=',', skiprows=1)
            np.testing.assert_allclose(inputs[:, 1], case['amplitude_deg'])
            replay = run_case(read_case(out / 'case.json'), out, Path(directory) / 'replay')
            self.assertEqual(result['summary'], replay['summary'])
            self.assertEqual(result['linearization'], replay['linearization'])

    def test_stopped_response_exports_actual_input_and_partial_plot(self):
        with TemporaryDirectory() as directory:
            source = ROOT / 'examples/open-loop'
            case = read_case(source / 'uh60-response.json')
            case.update(duration_s=.1, time_step_s=.005, radial_stations=24, azimuth_stations=24,
                        input_type='pulse', input_start_s=.02, input_duration_s=.05)
            history = np.zeros((2, 31))
            history[:, 0] = [.02, .03]
            failure = ResponseDomainError('injected export-path limit', history)
            out = Path(directory) / 'stopped'
            with patch('rotordesignlab.open_loop.step_response', side_effect=failure):
                result = run_case(case, source, out)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['solver_status'], 'response_stopped')
            self.assertEqual(result['summary']['last_valid_time_s'], .03)
            self.assertFalse((out / 'response.csv').exists())
            for name in ('partial-response.csv', 'input.csv', 'input.png', 'response.png'):
                self.assertTrue((out / name).exists())
            inputs = np.loadtxt(out / 'input.csv', delimiter=',', skiprows=1)
            wave = from_case(case)
            np.testing.assert_allclose(inputs[:, 1], [wave.value_deg(t) for t in history[:, 0]])
            self.assertIn('仅最后有效段', (out / 'response.svg').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
