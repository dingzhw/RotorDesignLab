"""A3 causal diagnostics. Frozen interpolation segments are experiments, not a solver option.

Existing snapshots and failures remain byte-identical. DOP853 is an independent
diagnostic integrator; production RK4 is checked separately for the 2-second run.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import root
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.cases import write_json
from rotordesignlab.coupled_dynamics import CoupledDynamics
from rotordesignlab.dynamics import central_derivatives, derivative_check
from rotordesignlab.perturbation import Perturbation
from rotordesignlab.trim import TrimSystem


def load_point(folder, refine=False):
    base = folder/'trim'
    case = json.loads((base/'case.json').read_text(encoding='utf-8'))
    result = json.loads((base/'result.json').read_text(encoding='utf-8'))
    system = TrimSystem(read_aircraft(base/'aircraft.json'), base, case)
    state = np.array(result['diagnostics']['solved_state'])
    if refine:
        fit = root(lambda x: system.evaluate(x)[0], state, tol=1e-11)
        residual, data = system.evaluate(fit.x, strict=True)
        if np.max(abs(residual)) > 1e-10 or np.max(abs(fit.x-state)) > 1e-5:
            raise ValueError('Refinement failed its fixed residual/proximity criteria')
        state = fit.x
        velocity = data['velocity']
    else:
        velocity = result['velocity_body_m_s']
    plant = CoupledDynamics(system, state, velocity)
    matrix = np.load(folder/'matrices.npz')
    if not refine:
        np.testing.assert_array_equal(plant.state, matrix['state'])
        np.testing.assert_array_equal(plant.mass_matrix, matrix['E'])
    return plant, matrix['A'], matrix['B']


class FrozenSegments:
    """Continue only the segment active at trim, per element, for causal isolation.

    This deliberately changes off-trim aerodynamics. It must NEVER be selected
    silently in product trim, linearization or response calculations.
    """
    def __init__(self, polar, alpha):
        self.polar = polar
        self.alpha = alpha.copy()
        index = np.clip(np.searchsorted(polar[:, 0], alpha, side='right')-1, 0, len(polar)-2)
        self.slopes = (polar[index+1, 1:]-polar[index, 1:])/(polar[index+1, 0]-polar[index, 0])[..., None]
        self.values = np.stack([np.interp(alpha, polar[:, 0], polar[:, i]) for i in (1, 2)], axis=-1)

    def coefficients(self, radius, alpha, mach, reynolds=None, strict=True):
        if strict and (np.min(alpha) < self.polar[0, 0] or np.max(alpha) > self.polar[-1, 0]):
            raise ValueError('Frozen-segment diagnostic left original alpha domain')
        values = self.values+self.slopes*(alpha-self.alpha)[..., None]
        return values[..., 0], values[..., 1]


def freeze_segments(plant, roles=('main', 'tail')):
    frozen = deepcopy(plant)
    _, data = frozen.evaluate(frozen.state, frozen.controls)
    for role in roles:
        model = frozen.system.rotors[role]
        if model.rotor.airfoil_grid is not None:
            raise ValueError('Causal diagnostic only implemented for single CSV polars')
        polar = FrozenSegments(model.rotor.polar, data['rotor_data'][role]['alpha_deg'])
        model.rotor = replace(model.rotor, airfoil_grid=polar)
        model.kernel.rotor = model.rotor
    return frozen


def integrate(plant, a, b, amplitude, duration=.1, control=2, max_step=.0025,
              waveform=None, rtol=1e-10, atol=1e-12, sample_times=None):
    wave = waveform or Perturbation(kind='pulse', amplitude_deg=amplitude,
                                   start_s=duration*.1, duration_s=duration*.5)
    wave.validate(duration)
    size = len(plant.state)
    scale = plant.state_scale
    times = (np.linspace(0., duration, round(duration/.0005)+1)
             if sample_times is None else np.asarray(sample_times))

    def equation(time, combined):
        du = np.zeros(4)
        du[control] = np.deg2rad(wave.value_deg(float(time)))
        nonlinear = plant.rhs(plant.state+combined[:size]*scale, plant.controls+du)/scale
        linear = (a@(combined[size:]*scale)+b@du)/scale
        return np.r_[nonlinear, linear]

    solution = solve_ivp(equation, (0., duration), np.zeros(2*size), method='DOP853',
                         t_eval=times, max_step=max_step, rtol=rtol, atol=atol)
    if not solution.success or len(solution.t) != len(times):
        raise ValueError(solution.message)
    return np.column_stack((solution.t, solution.y.T*np.tile(scale, 2))), solution.nfev


def error_metrics(history, plant, drift=None):
    size = len(plant.state)
    error = (history[:, 1:size+1]-history[:, size+1:])/plant.state_scale
    peak = float(np.max(abs(error)))
    i, j = np.unravel_index(np.argmax(abs(error)), error.shape)
    result = dict(scaled_peak_error=peak, peak_state=plant.state_names[j], peak_time_s=float(history[i, 0]))
    if drift is not None:
        result['drift_subtracted_peak_error_diagnostic_only'] = float(np.max(abs(
            error-drift[:, 1:size+1]/plant.state_scale)))
    return result


def confirm(points, responses, out):
    """Check production trajectories independently and isolate main-rotor knots."""
    checks = []
    for label in ('synthetic-15-n24', 'oh6-20.58-n24'):
        plant, a, b = load_point(points/label)
        files = list((responses/(label+'-c2')).glob('response-2-0.02-*.npy'))
        if not files:
            raise ValueError(f'No original production trajectories: {label}')
        saved = max((np.load(path) for path in files), key=len)
        tight, _ = integrate(plant, a, b, .02, max_step=.00125, rtol=1e-11,
                             atol=1e-13, sample_times=saved[:, 0])
        np.save(out/(label+'-tight.npy'), tight)
        size = len(plant.state)
        peaks = np.maximum(np.max(abs(tight[:, 1:size+1]), axis=0), 1e-9)
        difference = float(np.max(np.max(abs(tight[:, 1:size+1]-saved[:, 1:size+1]), axis=0)/peaks))
        refined, _, _ = load_point(points/label, refine=True)
        frozen = freeze_segments(refined, ('main',))
        np.testing.assert_allclose(frozen.rhs(frozen.state, frozen.controls),
                                   refined.rhs(refined.state, refined.controls), rtol=0, atol=1e-10)
        fa, fb = central_derivatives(frozen, .0125)
        errors = []
        for amplitude in (.02, .01):
            history, _ = integrate(frozen, fa, fb, amplitude)
            np.save(out/f'{label}-main-only-{amplitude:g}.npy', history)
            errors.append(error_metrics(history, frozen)['scaled_peak_error'])
        checks.append(dict(label=label, independent_integrator_relative_difference=difference,
                           passed=difference <= .01, main_only_frozen_ratio=errors[1]/errors[0], errors=errors))
        write_json(out/'checks.json', checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--points', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--confirm-responses', type=Path,
                        help='Run independent confirmation only, against an original short-response directory')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    if args.confirm_responses:
        confirm(args.points, args.confirm_responses, args.out)
        return
    records = []
    start = perf_counter()
    for label in ('synthetic-15-n24', 'oh6-20.58-n24'):
        original, old_a, old_b = load_point(args.points/label)
        fine_a, fine_b = central_derivatives(original, .025)
        finer_a, finer_b = central_derivatives(original, .0125)
        variants = [('original', original, old_a, old_b),
                    ('local_jacobian', original, finer_a, finer_b)]
        refined, _, _ = load_point(args.points/label, refine=True)
        variants.append(('refined_equilibrium', refined, *central_derivatives(refined, .0125)))
        frozen = freeze_segments(refined)
        variants.append(('frozen_segments_diagnostic', frozen, *central_derivatives(frozen, .0125)))
        for name, plant, a, b in variants:
            folder = args.out/label/name
            folder.mkdir(parents=True)
            zero, calls = integrate(plant, a, b, 0.)
            np.save(folder/'zero.npy', zero)
            item = dict(label=label, variant=name,
                equilibrium_scaled_rhs=float(np.max(abs(plant.rhs(plant.state, plant.controls)/plant.state_scale))),
                zero_scaled_drift=float(np.max(abs(zero[:, 1:len(plant.state)+1]/plant.state_scale))),
                control_jacobian_change_scaled=float(np.max(abs((b-old_b)*np.deg2rad(1.)/plant.state_scale[:, None]))),
                amplitudes=[], fine_difference_check=derivative_check(fine_a, fine_b, finer_a, finer_b, original.state_scale))
            for amplitude in (.02, .01, -.02, -.01, .002, .001, -.002, -.001):
                history, calls = integrate(plant, a, b, amplitude)
                np.save(folder/f'{amplitude:g}.npy', history)
                item['amplitudes'].append(dict(amplitude_deg=amplitude, nfev=calls,
                                               **error_metrics(history, plant, zero)))
                write_json(folder/'checks.json', item)
            records.append(item)
            write_json(args.out/'checks.json', records)
            print(label, name, f'{perf_counter()-start:.1f}s', flush=True)
    write_json(args.out/'manifest.json', dict(
        elapsed_s=perf_counter()-start, tolerances=dict(rtol=1e-10, atol_scaled=1e-12, max_step_s=.0025),
        source_matrix_hashes={label: sha256((args.points/label/'matrices.npz').read_bytes()).hexdigest()
                              for label in ('synthetic-15-n24', 'oh6-20.58-n24')},
        frozen_segment_role='causal experiment only; not an accepted airfoil model',
        input='sin2 pulse start .01s width .05s; control index 2; 0.1s observation'))


if __name__ == '__main__':
    main()
