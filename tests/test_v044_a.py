"""Regression checks for v0.4.4-A domain and result reliability fixes."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np

from rotordesignlab.airfoils import AirfoilGrid
from rotordesignlab.aircraft import snapshot_aircraft
from rotordesignlab.azimuth import AzimuthRotor
from rotordesignlab.batch import run_batch
from rotordesignlab.cases import THREE_BLADE, read_case, read_rotor, run_case, write_json
from rotordesignlab.dynamics import modes
from rotordesignlab.inverse import solve_target
from rotordesignlab.rotor import solve

ROOT = Path(__file__).resolve().parents[1]


def mach_grid(polar, maximum=1.2):
    tables = {}
    for index, key in enumerate(('cl', 'cd'), start=1):
        tables[key] = dict(alpha_deg=polar[:, 0].tolist(), mach=[0., maximum],
                           values=np.repeat(polar[:, index, None], 2, axis=1).tolist())
    return dict(schema_version=1, kind='spanwise_airfoil', span_boundary='hold_endpoint',
                sections=[dict(r_over_R=.5, **tables)])


class ReliabilityTests(unittest.TestCase):
    def test_local_speed_and_mach_domain_for_axial_spatial_and_inverse(self):
        rotor, _ = read_rotor(read_case(THREE_BLADE), THREE_BLADE.parent)
        fast = replace(rotor, omega=280 / rotor.radius)
        for model in (fast, replace(fast, inflow_model='annular')):
            with self.assertRaisesRegex(ValueError, '250'):
                solve(model)
        with self.assertRaisesRegex(ValueError, '250'):
            AzimuthRotor(fast).elements([.2, 0, 0], [.05, 0, 0], [0, 0, 0], [0, 0, 0])
        supported = replace(fast, airfoil_grid=AirfoilGrid(mach_grid(rotor.polar)))
        summary, _, _ = solve(supported)
        self.assertGreater(summary['mach_max'], 250 / supported.speed_of_sound)
        _, inverse, _ = solve_target(supported, dict(thrust_n=summary['thrust_n'], solve_for='rpm',
                                      bounds=[260 / rotor.radius * 30 / np.pi, 300 / rotor.radius * 30 / np.pi]), {'rpm': [1, 30000]})
        self.assertAlmostEqual(inverse[0]['thrust_n'], summary['thrust_n'], places=6)
        limited = replace(supported, airfoil_grid=AirfoilGrid(mach_grid(rotor.polar, .5)))
        with self.assertRaisesRegex(ValueError, 'Mach'):
            solve(limited)
        with self.assertRaisesRegex(ValueError, 'Mach'):
            AzimuthRotor(limited).elements([.2, 0, 0], [.05, 0, 0], [0, 0, 0], [0, 0, 0])

    def test_parser_and_batch_above_old_tip_gate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'inputs').mkdir()
            source = ROOT / 'examples/synthetic-aircraft.json'
            aircraft = snapshot_aircraft(read_case(source), source.parent, root / 'inputs')
            rotor = aircraft['rotors'][0]
            polar = np.loadtxt(root / 'inputs' / rotor.pop('polar_csv'), delimiter=',', skiprows=1)
            rotor['polar_json'] = 'mach.json'
            rotor['limits']['rpm'] = [800, 3000]
            write_json(root / 'inputs/mach.json', mach_grid(polar))
            write_json(root / 'inputs/aircraft.json', aircraft)
            case = dict(schema_version=2, model='aircraft_rotor', aircraft_json='aircraft.json',
                        rotor_id=rotor['id'], rpm=2500, collective_deg=13, axial_speed_m_s=0)
            write_json(root / 'inputs/case.json', case)
            spec = dict(schema_version=1, kind='rotor_sweep', case_json='case.json', axes={'rpm': [2400, 2500]})
            answer = run_batch(spec, root / 'inputs', root / 'batch')
            self.assertEqual(answer['status'], 'converged', answer)
            self.assertEqual(answer['analysis_model'], 'aircraft_rotor')
            self.assertIn('孤立旋翼轴流性能', (root / 'batch/performance.svg').read_text(encoding='utf-8'))
            spatial = dict(case, model='spatial_rotor', flow_body_m_s=[0, 0, 0], flapping_model='fixed')
            spatial.pop('axial_speed_m_s')
            write_json(root / 'inputs/case.json', spatial)
            answer = run_batch(spec, root / 'inputs', root / 'spatial-batch')
            self.assertEqual(answer['status'], 'converged', answer)
            self.assertIn('孤立旋翼三方向性能', (root / 'spatial-batch/performance.svg').read_text(encoding='utf-8'))
            self.assertIn('独立试验', answer['model_maturity'])

    def test_modal_defect_and_repeated_diagonalizable_roots(self):
        diagonal = np.diag(-np.arange(1., 16.))
        diagonal[1, 1] = diagonal[0, 0]
        good = modes(diagonal)
        self.assertTrue(all(m['participation_status'] == 'available' for m in good))
        self.assertEqual(sum(m['repeated_eigenvalue'] for m in good), 2)
        jordan = deepcopy(diagonal)
        jordan[0, 1] = 1
        bad = modes(jordan)
        self.assertEqual(len(bad), 15)
        self.assertTrue(all(m['participation_status'] == 'unavailable' for m in bad))
        self.assertTrue(all(m['participation'] == {} for m in bad))
        self.assertTrue(all(m['eigenpair_relative_residual'] < 1e-10 for m in bad))
        jordan[1, 1] += 1e-10
        self.assertTrue(all(m['participation_status'] == 'unavailable' for m in modes(jordan)))

    def test_duration_rejection_preserves_maturity(self):
        with TemporaryDirectory() as directory:
            case = dict(schema_version=3, model='helicopter', analysis='response', aircraft_json='missing.json',
                        control='main_collective', amplitude_deg=.05, duration_s=.01, time_step_s=.001)
            result = run_case(case, ROOT, Path(directory) / 'invalid')
            self.assertEqual(result['status'], 'failed')
            self.assertIn('duration_s', result['error'])
            self.assertIn('试验性', result['model_maturity'])
            self.assertEqual(result['design_limits_status'], 'not_evaluated')


if __name__ == '__main__':
    unittest.main()
