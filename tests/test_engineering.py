from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from rotordesignlab.aircraft import installed_loads, read_aircraft
from rotordesignlab.batch import run_batch
from rotordesignlab.cases import EXAMPLES, read_case, run_case, write_json


class EngineeringTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for name in ('synthetic-aircraft.json', 'synthetic-geometry.csv', 'synthetic-polar.csv'):
            shutil.copyfile(EXAMPLES / name, self.base / name)
        self.aircraft = read_case(self.base / 'synthetic-aircraft.json')
        self.case = read_case(EXAMPLES / 'engineering-rotor.json')

    def test_known_forward_point_recovered_by_both_inverse_modes(self):
        for speed in (0, 25):
            case = dict(self.case, axial_speed_m_s=speed)
            forward = run_case(case, self.base, self.base / f'forward-{speed}')
            self.assertEqual(forward['status'], 'converged', forward)
            for variable, expected in (('rpm', 1700), ('collective_deg', 17)):
                target = dict(thrust_n=forward['summary']['thrust_n'], solve_for=variable)
                result = run_case(dict(case, target=target), self.base, self.base / f'inverse-{speed}-{variable}')
                self.assertEqual(result['status'], 'converged', result)
                self.assertLess(result['target_solution']['relative_thrust_error'], 1e-8)
                self.assertAlmostEqual(result['target_solution']['value'], expected, places=6)
                self.assertAlmostEqual(result['summary']['power_coefficient'], result['summary']['torque_coefficient'])

    def test_failed_target_and_limits_are_distinct(self):
        for index, target in enumerate(({'thrust_n': -1, 'solve_for': 'rpm'},
                                        {'thrust_n': 1e6, 'solve_for': 'collective_deg'},
                                        {'thrust_n': 2000, 'solve_for': 'rpm', 'bounds': [0, 1000]})):
            out = self.base / f'bad-{index}'
            result = run_case(dict(self.case, target=target), self.base, out)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('error', result)
            self.assertTrue((out / 'result.json').is_file())
            self.assertFalse((out / 'run.lock').exists())
        self.aircraft['rotors'][0]['limits']['power_w'] = 1
        write_json(self.base / 'synthetic-aircraft.json', self.aircraft)
        result = run_case(self.case, self.base, self.base / 'limited')
        self.assertEqual(result['status'], 'converged')
        self.assertFalse(result['feasible'])
        self.assertLess(result['installation']['margins']['power_w'], 0)

    def test_ambiguous_target_requires_narrower_bounds(self):
        target = dict(thrust_n=2800, solve_for='collective_deg')
        ambiguous = run_case(dict(self.case, target=target), self.base, self.base / 'ambiguous')
        self.assertEqual(ambiguous['status'], 'failed')
        self.assertIn('多个有效解', ambiguous['error'])
        target['bounds'] = [12, 20]
        selected = run_case(dict(self.case, target=target), self.base, self.base / 'selected')
        self.assertEqual(selected['status'], 'converged', selected)
        self.assertLess(selected['target_solution']['relative_thrust_error'], 1e-8)

    def test_aircraft_coordinates_and_torque_reaction(self):
        model = deepcopy(self.aircraft)
        model['mass_properties']['cg_m'] = [0.1, 0, 0]
        rotor = model['rotors'][0]
        rotor['position_m'] = [0.2, 0.3, -0.6]
        for sign in (1, -1):
            rotor['rotation_sign'] = sign
            loads = installed_loads(model, rotor, {'thrust_n': 100, 'torque_nm': 10, 'power_w': 200})
            np.testing.assert_allclose(loads['force_body_n'], [0, 0, -100])
            np.testing.assert_allclose(loads['moment_cg_body_nm'], [-30, 10, sign * 10], atol=1e-12)

    def test_invalid_aircraft_data(self):
        models = []
        for inertia in ([[-1, 0, 0], [0, 2, 0], [0, 0, 2]],
                        [[1, 0, 0], [0, 1, 0], [0, 0, 3]],
                        [[2, 1, 0], [0, 2, 0], [0, 0, 2]]):
            model = deepcopy(self.aircraft)
            model['mass_properties']['inertia_cg_kg_m2'] = inertia
            models.append(model)
        model = deepcopy(self.aircraft); model['rotors'][0]['thrust_axis_body'] = [0, 0, -2]; models.append(model)
        model = deepcopy(self.aircraft); model['rotors'].append(model['rotors'][0]); models.append(model)
        model = deepcopy(self.aircraft); model['schema_version'] = True; models.append(model)
        model = deepcopy(self.aircraft); model['units'] = 'imperial'; models.append(model)
        for index, model in enumerate(models):
            path = self.base / f'invalid-{index}.json'
            write_json(path, model)
            with self.subTest(index=index), self.assertRaises(ValueError):
                read_aircraft(path)

    def test_portable_snapshot_and_solved_case(self):
        target = dict(thrust_n=2000, solve_for='collective_deg')
        output = self.base / 'target'
        first = run_case(dict(self.case, target=target), self.base, output)
        moved = self.base / 'relocated'
        shutil.copytree(output, moved)
        hashes = read_case(moved / 'input-sha256.json')
        for name, digest in hashes.items():
            self.assertEqual(hashlib.sha256((moved / name).read_bytes()).hexdigest(), digest)
        replay = run_case(read_case(moved / 'case.json'), moved, self.base / 'replay')
        self.assertEqual(first['summary'], replay['summary'])
        solved = run_case(read_case(moved / 'solved-case.json'), moved, self.base / 'solved')
        self.assertAlmostEqual(solved['summary']['thrust_n'], 2000, places=7)
        self.assertNotIn('target_solution', solved)

    def test_batch_failure_rows_and_replay(self):
        write_json(self.base / 'case.json', self.case)
        self.aircraft['rotors'][0]['limits']['power_w'] = 1
        write_json(self.base / 'synthetic-aircraft.json', self.aircraft)
        spec = dict(schema_version=1, kind='rotor_sweep', case_json='case.json',
                    axes={'rpm': [1400, 1700, 30000], 'collective_deg': [12, 20]})
        output = self.base / 'batch'
        result = run_batch(spec, self.base, output)
        self.assertEqual(result['status'], 'partial', result)
        self.assertEqual(result['summary'], dict(total=6, converged=4, failed=2, limit_violations=4))
        with (output / 'performance.csv').open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(bool(row['error']) for row in rows), 2)
        self.assertTrue((output / 'performance.png').read_bytes().startswith(b'\x89PNG'))
        replay = run_batch(read_case(output / 'batch.json'), output, self.base / 'batch-replay')
        self.assertEqual(result['summary'], replay['summary'])
        self.assertEqual((output / 'performance.csv').read_bytes(), (self.base / 'batch-replay' / 'performance.csv').read_bytes())

    def test_batch_rejects_conflicting_target_axis(self):
        write_json(self.base / 'case.json', dict(self.case, target={'thrust_n': 2000, 'solve_for': 'rpm'}))
        spec = dict(schema_version=1, kind='rotor_sweep', case_json='case.json', axes={'rpm': [1500, 1700]})
        result = run_batch(spec, self.base, self.base / 'conflict')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('反求变量', result['error'])


if __name__ == '__main__':
    unittest.main()
