"""Public two-template trim, linearization and short-response basis covariance."""
from pathlib import Path
import sys
import numpy as np
from rotordesignlab.cases import run_case, read_case, write_json
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.trim import TrimSystem
from rotordesignlab.dynamics import ReducedDynamics, step_response
from rotordesignlab.perturbation import Perturbation

ROOT = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=False)
summary = []
state_sign = np.ones(15)
state_sign[10:12] = -1
control_sign = np.array([1, -1, -1, 1])
trim_sign = np.ones(18)
trim_sign[[1, 2, 7, 8, 10, 11]] = -1
for stem in ('synthetic', 'uh60-public'):
    for speed in (0., 20.):
        results = []
        for version in ('v044', 'v045'):
            base = ROOT / f'examples/templates/{version}'
            case = dict(schema_version=3, model='helicopter', analysis='linearize', aircraft_json=stem + '.json',
                        speed_m_s=speed, climb_m_s=0., altitude_m=0., requested_duration_s=60.,
                        radial_stations=24, azimuth_stations=24, frequencies_rad_s=[.1, 1.])
            directory = output / f'{stem}-{speed:g}-{version}'
            answer = run_case(case, base, directory)
            assert answer['status'] == 'converged', answer
            trim = read_case(directory / 'trim/result.json')
            system = TrimSystem(read_aircraft(directory / 'trim/aircraft.json'), directory / 'trim', read_case(directory / 'trim/case.json'))
            plant = ReducedDynamics(system, trim['diagnostics']['solved_state'], trim['velocity_body_m_s'])
            a = np.loadtxt(directory / 'A.csv', delimiter=',', skiprows=1, usecols=range(1, 16))
            b = np.loadtxt(directory / 'B.csv', delimiter=',', skiprows=1, usecols=range(1, 5))
            results.append((trim, plant, a, b))
        old, new = results
        expected_a = old[2] * state_sign[:, None] * state_sign[None, :]
        expected_b = old[3] * state_sign[:, None] * control_sign[None, :]
        # Absolute floor protects zero entries; whole-matrix relative norm is also saved.
        np.testing.assert_allclose(new[2], expected_a, atol=1e-5, rtol=2e-5)
        np.testing.assert_allclose(new[3], expected_b, atol=1e-5, rtol=2e-5)
        np.testing.assert_allclose(new[1].trim, old[1].trim * trim_sign, atol=2e-7, rtol=2e-5)
        histories = []
        for index, (_, plant, a, b) in enumerate(results):
            wave = Perturbation('pulse', .01 if index == 0 else -.01, .005, .01)
            histories.append(step_response(plant, a, b, 1, wave.amplitude_deg, .025, .001, perturbation=wave))
        expected = histories[0].copy()
        expected[:, 1:16] *= state_sign
        expected[:, 16:] *= state_sign
        np.testing.assert_allclose(histories[1], expected, atol=2e-8, rtol=2e-4)
        row = dict(template=stem, speed_m_s=speed, radial_stations=24, azimuth_stations=24,
                   maximum_trim_state_difference=float(np.max(abs(new[1].trim - old[1].trim * trim_sign))),
                   A_relative_norm=float(np.linalg.norm(new[2] - expected_a) / np.linalg.norm(expected_a)),
                   B_relative_norm=float(np.linalg.norm(new[3] - expected_b) / np.linalg.norm(expected_b)),
                   response_max_absolute_difference=float(np.max(abs(histories[1] - expected))),
                   response_duration_s=.025, response_step_s=.001, passed=True)
        summary.append(row)
        write_json(output / 'summary.json', summary)
        print(stem, speed, row, flush=True)
public = ROOT / 'validation/v045/b-coordinate-checks.json'
public.parent.mkdir(parents=True, exist_ok=True)
write_json(public, dict(checks=summary,
           definition='New main basis = old basis @ diag(-1,-1,1); harmonic controls, inflow and flap mapped consistently.',
           scope='Coordinate covariance and software replay; not independent aerodynamic or dynamic validation.'))
