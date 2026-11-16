"""Bounded response matrix: two templates, hover/20 m/s, four controls, three inputs.

Run: python tests/check_v044_b.py <empty-output-directory> [workers=4]
Each independent job checkpoints its result; no shared solver state or fitted data.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

# Bound native math threads before NumPy/SciPy are imported in worker processes.
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np
from rotordesignlab import designs, __version__
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.cases import read_case, run_case, write_json
from rotordesignlab.trim import TrimSystem
from rotordesignlab.dynamics import ReducedDynamics, CONTROLS, STATE_SCALE, step_response, ResponseDomainError
from rotordesignlab.perturbation import Perturbation


def trial(plant, a, b, control, wave, step):
    started = perf_counter()
    try:
        history = step_response(plant, a, b, control, wave.amplitude_deg, 2., step, perturbation=wave)
        status, error = 'complete', None
    except ResponseDomainError as failure:
        history, status, error = failure.history, 'stopped', str(failure)
    assert len(history) and np.isfinite(history).all()
    discrepancy = (history[:, 1:16] - history[:, 16:]) / STATE_SCALE
    return history, dict(status=status, error=error, end_s=float(history[-1, 0]),
                         scaled_nonlinear_linear_error=float(np.max(np.linalg.norm(discrepancy, axis=1))),
                         elapsed_s=perf_counter() - started, time_step_s=step)


def run_job(directory, control, kind):
    directory = Path(directory)
    case = read_case(directory / 'trim/case.json')
    aircraft = read_aircraft(directory / 'trim/aircraft.json')
    trim = read_case(directory / 'trim/result.json')
    system = TrimSystem(aircraft, directory / 'trim', case)
    plant = ReducedDynamics(system, trim['diagnostics']['solved_state'], trim['velocity_body_m_s'])
    a = np.loadtxt(directory / 'A.csv', delimiter=',', skiprows=1, usecols=range(1, 16))
    b = np.loadtxt(directory / 'B.csv', delimiter=',', skiprows=1, usecols=range(1, 5))
    fastest = float(max(abs(np.linalg.eigvals(a))))
    step = next(h for h in (.01, .005, .002, .001, .0005) if h * fastest <= 1)
    wave = Perturbation(kind, .05, .2, .5)
    history, summary = trial(plant, a, b, control, wave, step)
    peak = float(np.max(np.linalg.norm(history[:, 1:16] / STATE_SCALE, axis=1)))
    summary['scaled_response_peak'] = peak
    summary['nonlinear_linear_relative_error'] = summary['scaled_nonlinear_linear_error'] / max(peak, 1e-12)
    name = f'{CONTROLS[control]}-{kind}'
    np.savez_compressed(directory / (name + '.npz'), history=history,
                        input_deg=[wave.value_deg(t) for t in history[:, 0]])
    result = dict(base=directory.name, control=CONTROLS[control], input=wave.metadata(),
                  fastest_eigenvalue_magnitude=fastest, baseline=summary)
    # All controls/base points get time-step and amplitude refinement for the
    # new smooth default; analytic tests separately cover square-wave knots.
    if kind == 'pulse':
        fine, fine_info = trial(plant, a, b, control, wave, step / 2)
        half, half_info = trial(plant, a, b, control, replace(wave, amplitude_deg=.025), step)
        end = min(history[-1, 0], fine[-1, 0], half[-1, 0])
        valid = history[:, 0] <= end + 1e-12
        time = history[valid, 0]
        refined = np.column_stack([np.interp(time, fine[:, 0], fine[:, i]) for i in range(1, 16)])
        peak = max(float(np.max(np.linalg.norm(history[valid, 1:16] / STATE_SCALE, axis=1))), 1e-8)
        change = float(np.max(np.linalg.norm((history[valid, 1:16] - refined) / STATE_SCALE, axis=1))) / peak
        full_error = np.max(np.linalg.norm((history[valid, 1:16] - history[valid, 16:]) / STATE_SCALE, axis=1))
        half_valid = half[:, 0] <= end + 1e-12
        half_error = np.max(np.linalg.norm((half[half_valid, 1:16] - half[half_valid, 16:]) / STATE_SCALE, axis=1))
        ratio = float(half_error / full_error) if full_error > 1e-8 else None
        result['refinement'] = dict(fine=fine_info, half_amplitude=half_info, compared_until_s=float(end),
                                    time_step_relative_change=change, amplitude_error_ratio=ratio,
                                    time_step_pass=change <= .01, amplitude_pass=ratio is None or ratio <= .65)
    write_json(directory / (name + '.json'), result)
    return result


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    bases = []
    for index, name in enumerate(list(designs.TEMPLATES)[:2]):
        path = designs.materialize(designs.from_template(name), root / f'inputs-{index}')
        for speed in (0., 20.):
            case = dict(schema_version=3, model='helicopter', analysis='linearize', aircraft_json=str(path),
                        altitude_m=0., speed_m_s=speed, climb_m_s=0., requested_duration_s=600.,
                        radial_stations=24, azimuth_stations=24)
            out = root / f'model-{index}-speed-{speed:g}'
            result = run_case(case, root, out)
            assert result['status'] == 'converged', result
            assert result['download_model']['strategy'] == 'none'
            bases.append(out)
            print(f'Base passed: {out.name}', flush=True)
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        tasks = [pool.submit(run_job, str(base), control, kind)
                 for base in bases for control in range(4) for kind in ('step', 'pulse', 'doublet')]
        for future in as_completed(tasks):
            item = future.result()
            results.append(item)
            write_json(root / 'checkpoint.json', results)
            print(f"{len(results)}/48 {item['base']} {item['control']} {item['input']['type']}: {item['baseline']['status']}", flush=True)
    checks = [r['refinement'] for r in results if 'refinement' in r]
    payload = dict(solver_version=__version__, python=platform.python_version(), processor=platform.processor(),
                   logical_cpu_count=os.cpu_count(), workers=workers, native_threads_per_worker=1,
                   grid=dict(radial=24, azimuth=24), cases=sorted(results, key=lambda r: (r['base'], r['control'], r['input']['type'])),
                   passed=all(r['time_step_pass'] and r['amplitude_pass'] for r in checks))
    write_json(root / 'summary.json', payload)
    assert payload['passed'], 'Refinement failed; inspect summary.json, do not relax thresholds.'
    print('All waveform and refinement checks passed.', flush=True)


if __name__ == '__main__':
    main()
