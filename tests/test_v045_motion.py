"""Physical heading/body conversion, both rotor roles, inverse and replay."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import numpy as np
from rotordesignlab import designs
from rotordesignlab.cases import read_case, run_case, write_json
from rotordesignlab.batch import run_batch
from rotordesignlab.coordinates import motion_to_flow, flow_to_motion, canonical_spatial_case, attitude_matrix


class MotionTests(unittest.TestCase):
    def test_known_axes_and_round_trip(self):
        np.testing.assert_allclose(motion_to_flow([20, 0, 3]), [-20, 0, 3])
        np.testing.assert_allclose(motion_to_flow([0, 0, 3], [90, 0]), [0, 3, 0], atol=1e-14)
        np.testing.assert_allclose(motion_to_flow([20, 0, 0], [0, 30]), [-10*np.sqrt(3), 0, -10], atol=1e-14)
        for angles in ([20, -10], [-15, 25], [170, 80]):
            for motion in ([20, 3, 4], [-10, -2, 5]):
                flow = motion_to_flow(motion, angles)
                np.testing.assert_allclose(flow_to_motion(flow, angles), motion, atol=1e-12)
                self.assertAlmostEqual(np.linalg.norm(flow), np.linalg.norm(motion))
        np.testing.assert_allclose(attitude_matrix([90, 0]).T @ [0, 0, 9.80665], [0, 9.80665, 0], atol=1e-14)

    def test_invalid_or_ambiguous_inputs(self):
        for case in ({}, {'motion_m_s': [1, 2]}, {'flow_body_m_s': [0, 0, 0], 'motion_m_s': [0, 0, 0]},
                     {'motion_m_s': [True, 0, 0]}, {'motion_m_s': [1, 0, 0], 'attitude_deg': [0, 90]},
                     {'flow_body_m_s': [float('nan'), 0, 0]}, {'motion_m_s': [150, 150, 0]}):
            with self.assertRaises(ValueError):
                canonical_spatial_case(case)

    @patch('rotordesignlab.isolated.plot_elements')
    def test_two_templates_roles_rotation_and_portable_replay(self, _):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, template in enumerate(list(designs.TEMPLATES)[:2]):
                design = designs.from_template(template)
                inputs = root / str(index)
                designs.materialize(design, inputs)
                for sign in (1, -1):
                    aircraft = read_case(inputs / 'aircraft.json')
                    for rotor in aircraft['rotors']:
                        rotor['rotation_sign'] = sign
                    write_json(inputs / 'aircraft.json', aircraft)
                    for role in ('main', 'tail'):
                        case = dict(schema_version=2, model='spatial_rotor', aircraft_json='aircraft.json',
                                    rotor_id=role, motion_m_s=[12., 1., 3.], attitude_deg=[6., -4.],
                                    flapping_model='fixed', radial_stations=24, azimuth_stations=24)
                        out = root / f'{index}-{role}-{sign}'
                        result = run_case(case, inputs, out)
                        self.assertEqual(result['status'], 'converged', result)
                        snapshot = read_case(out / 'case.json')
                        self.assertNotIn('motion_m_s', snapshot)
                        np.testing.assert_allclose(snapshot['flow_body_m_s'], motion_to_flow(case['motion_m_s'], case['attitude_deg']))
                        replay = run_case(snapshot, out, root / (out.name + '-replay'))
                        self.assertEqual(result['summary'], replay['summary'])
                        self.assertEqual(result['installation'], replay['installation'])
                        np.testing.assert_allclose(result['gravity_body_m_s2'], attitude_matrix(case['attitude_deg']).T @ [0, 0, 9.80665])

    @patch('rotordesignlab.isolated.plot_elements')
    def test_motion_inverse_and_batch_axis_independent_of_view(self, _):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / 'inputs'
            designs.materialize(designs.from_template(next(iter(designs.TEMPLATES))), inputs)
            case = dict(schema_version=2, model='spatial_rotor', aircraft_json='aircraft.json', rotor_id='main',
                        motion_m_s=[10., 2., 3.], attitude_deg=[6., -4.], collective_deg=13., radial_stations=24)
            forward = run_case(case, inputs, root / 'forward')
            self.assertEqual(forward['status'], 'converged', forward)
            target = dict(thrust_n=forward['summary']['thrust_n'], solve_for='collective_deg', bounds=[10, 16])
            inverse = run_case(dict(case, target=target), inputs, root / 'inverse')
            self.assertEqual(inverse['status'], 'converged', inverse)
            self.assertAlmostEqual(inverse['summary']['collective_deg'], 13, places=6)
            write_json(inputs / 'case.json', case)
            spec = dict(schema_version=1, kind='rotor_sweep', case_json='case.json', axes={'motion_forward_m_s': [0., 12.]})
            batch = run_batch(spec, inputs, root / 'batch')
            self.assertEqual(batch['status'], 'converged', batch)
            for index, speed in enumerate((0., 12.)):
                saved = read_case(root / f'batch/case-{index:04d}/case.json')
                np.testing.assert_allclose(saved['flow_body_m_s'], motion_to_flow([speed, 2., 3.], [6., -4.]))
            replay = run_batch(read_case(root / 'batch/batch.json'), root / 'batch', root / 'batch-replay')
            self.assertEqual(batch['summary'], replay['summary'])


if __name__ == '__main__':
    unittest.main()
