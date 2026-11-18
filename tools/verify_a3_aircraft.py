"""Bounded A3 diagnostics, preserving legacy packages. Never tunes a model to a table.

python -m tools.verify_a3_aircraft --package OH6.rdl --out NEW_DIRECTORY
Full input snapshots and failure records stay in the requested directory.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from rotordesignlab import designs
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.cases import run_case, write_json, write_csv
from rotordesignlab.coupled_dynamics import CoupledDynamics
from rotordesignlab.dynamics import (ReducedDynamics, central_derivatives, derivative_check,
                                    modes, step_response)
from rotordesignlab.mass_partition import Partition, skew, spatial_mass, properties
from rotordesignlab.perturbation import Perturbation
from rotordesignlab.trim import TrimSystem
from tools.build_a2_example import synthetic


REFERENCE = Path(__file__).resolve().parents[1]/'validation/hub-loads/cr3144-reference.json'
CASE = dict(schema_version=3, model='helicopter', analysis='trim', climb_m_s=0.,
            altitude_m=0., requested_duration_s=180.)


def candidate(original, name, mass_factor=1., accessory_factor=1., inertia_hypothesis='source_as_total'):
    """Missing properties are deliberately synthetic, not identified from derivatives."""
    design = deepcopy(original)
    aircraft = design['aircraft']
    aircraft['dynamics'] = dict(model='harmonic_hub_v1', mass_reference='total_at_reference_flap',
        reference_flap_deg={r['id']: [0., 0., 0.] for r in aircraft['rotors']},
        provenance='A3诊断假设：原总质量/重心/惯量视为包含主尾桨及旋转桨毂的零挥舞方位平均值；原资料未确认该参考构型。')
    for rotor in aircraft['rotors']:
        flap = rotor['flight']['flapping']
        main = rotor['role'] == 'main'
        if main:
            mass = (17.9663 if name == 'oh6' else 256.9*.45359237)*mass_factor
            source = ('NTRS19710023917 Table I p54 whole blade 17.9663kg; outboard/configuration equivalence unconfirmed'
                      if name == 'oh6' else 'J-GenHel H60_constants.jl WBLADE=256.9lb; outboard/configuration equivalence unconfirmed')
            first, second = flap['first_mass_moment_kg_m'], flap['inertia_kg_m2']
        elif flap['mode'] == 'fixed':
            mass = .5*accessory_factor
            lo, hi = .1*rotor['radius_m'], rotor['radius_m']
            first = mass*(lo+hi)/2
            second = mass*(lo*lo+lo*hi+hi*hi)/3
            flap.update(first_mass_moment_kg_m=first, inertia_kg_m2=second)
            source = 'A3 synthetic tail: 0.5kg uniform 0.1R..R, all moments scaled together; not measured'
        else:
            first, second = flap['first_mass_moment_kg_m'], flap['inertia_kg_m2']
            mass = 1.5*first*first/second*accessory_factor
            source = 'A3 tail mass=1.5*m1^2/I lower-bound sensitivity; published moments retained, not measured mass'
        rotor['blade_mass'] = dict(mass_kg=mass, first_mass_moment_kg_m=first,
            inertia_kg_m2=second, provenance=f'{source}; mass_factor={mass_factor if main else accessory_factor:g}')
        hub_mass = (5. if main else .5) if name == 'oh6' else (30. if main else 2.)
        transverse = (.05 if main else .002) if name == 'oh6' else (.5 if main else .02)
        rotor['hub'] = dict(mass_kg=hub_mass*accessory_factor, cg_rotor_m=[0., 0., 0.],
            inertia_cg_kg_m2=(np.diag([transverse, transverse, 1.6*transverse])*accessory_factor).tolist(),
            provenance=f'A3 synthetic axisymmetric rotating hub: base mass {hub_mass:g}kg, Jxx={transverse:g}kgm2, factor={accessory_factor:g}; not measured')
    if inertia_hypothesis == 'source_as_core':
        props = aircraft['mass_properties']
        mass = props['mass_kg']
        source_inertia = np.array(props['inertia_cg_kg_m2'])
        # Extract rotor reference inertia without modifying any measured tensor.
        # The large temporary tensor is only an algebraic device for Partition;
        # it is never a solver input. Final tensor is rebuilt from explicit parts.
        temporary = deepcopy(aircraft)
        temporary['mass_properties']['inertia_cg_kg_m2'] = (np.eye(3)*1e6).tolist()
        partition = Partition(temporary)
        rotating = spatial_mass(mass, np.zeros(3), np.eye(3)*1e6)-partition.core_matrix
        rotating_mass, rotating_cg, _ = properties(rotating)
        core_mass = mass-rotating_mass
        core_cg = -rotating_mass*rotating_cg/core_mass
        total = spatial_mass(core_mass, core_cg, source_inertia)+rotating
        props['inertia_cg_kg_m2'] = total[3:, 3:].tolist()
        props['provenance'] += (' A3 alternative hypothesis ONLY: original tensor assigned to nonrotating core; '
            'new total tensor assembled from core and estimated rotor parts, total mass/CG retained. '
            f'Original core-candidate tensor={source_inertia.tolist()}. Not confirmed source interpretation.')
        aircraft['dynamics']['provenance'] = props['provenance']
    return design


def point(design, path, speed, grid, legacy=False):
    path.mkdir(parents=True, exist_ok=False)
    aircraft_path = designs.materialize(deepcopy(design), path/'input')
    case = dict(CASE, speed_m_s=speed, radial_stations=grid, azimuth_stations=grid,
                aircraft_json=str(aircraft_path.resolve()))
    result = run_case(case, path, path/'trim')
    if result['status'] != 'converged':
        raise ValueError(f"trim: {result.get('error', result['status'])}")
    system = TrimSystem(read_aircraft(path/'trim/aircraft.json'), path/'trim', case)
    cls = ReducedDynamics if legacy else CoupledDynamics
    plant = cls(system, result['diagnostics']['solved_state'], result['velocity_body_m_s'])
    a, b = central_derivatives(plant)
    half_a, half_b = central_derivatives(plant, .5)
    check = derivative_check(a, b, half_a, half_b, getattr(plant, 'state_scale', None))
    np.savez(path/'matrices.npz', A=half_a, B=half_b, E=plant.mass_matrix, state=plant.state)
    quasi_a = half_a[:9, :9]-half_a[:9, 9:]@np.linalg.solve(half_a[9:, 9:], half_a[9:, :9])
    quasi_b = half_b[:9]-half_a[:9, 9:]@np.linalg.solve(half_a[9:, 9:], half_b[9:])
    details = dict(summary=result['summary'], derivative_check=check,
        equilibrium_rhs_max=float(max(abs(plant.rhs(plant.state, plant.controls)))),
        quasi_A=quasi_a.tolist(), quasi_B=quasi_b.tolist(),
        frozen_A=half_a[:9, :9].tolist(), frozen_B=half_b[:9].tolist(),
        velocity=plant.state[:3].tolist(),
        modes=modes(half_a, getattr(plant, 'state_names', None)), state_count=len(plant.state),
        max_abs_eigenvalue=float(max(abs(np.linalg.eigvals(half_a)))),
        mass_partition=getattr(system.partition, 'report', None))
    write_json(path/'checks.json', details)
    return plant, half_a, half_b, details


def compare_reference(details, speed, label):
    reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
    table = next(c['values'] for c in reference['cases'] if c['speed_m_s'] == speed)
    row_indices = [0, 2, 4, 1, 3, 5]
    column_indices = [0, 2, 4, 1, 3, 5]
    # Fig II-2 gearing includes linkage compliance. The original OH6 package has
    # main x aft, z up: theta=theta0 - A1s*cos(psi) - B1s*sin(psi).
    # Positive tail collective raises +Y thrust at x<0 => negative yaw; DP gearing
    # is POSITIVE (Fig II-2), unlike the previous absolute-value-only comparison.
    gains = np.deg2rad([.155*.88*100/22.9, -.240*.75*100/31.8,
                       -.135*.75*100/29.2, .390*.67*100/9.3])
    records = []
    for assumption in ('frozen', 'quasi'):
        a = np.array(details[assumption+'_A'])
        b = np.array(details[assumption+'_B'])
        # vdot = aO - omega cross v. Remove this kinematic term for all rate
        # columns, including tiny v0 terms, not just the four principal entries.
        a[:3, 3:6] -= skew(np.array(details['velocity']))
        computed = np.column_stack((a[np.ix_(row_indices, column_indices)],
                                    b[np.ix_(row_indices, [0, 2, 1, 3])]*gains))
        for i, row in enumerate(reference['rows']):
            for j, column in enumerate(reference['columns']):
                expected, value = table[i][j], computed[i, j]
                records.append([label, speed, assumption, row, column, expected, float(value),
                                float(value-expected), float((value-expected)/abs(expected)*100)])
    return records


def response_check(plant, a, b, path, control, duration=.2, amplitude_deg=.02):
    """Predeclared 0.02/0.01deg pulse; h/2; componentwise peak floors 1e-9.

    High rotor frequencies set the explicit integration step, not just body modes.
    Linear/nonlinear difference should scale quadratically (half amplitude ~1/4).
    """
    spectral = float(max(abs(np.linalg.eigvals(a))))
    count = max(200, int(np.ceil(duration*spectral/.3)))
    # Keep pulse knots on both grids so identical samples can be compared.
    count = int(np.ceil(count/20))*20
    step = duration/count
    records = []
    for amplitude, dt in [(amplitude_deg, step), (amplitude_deg, step/2), (amplitude_deg/2, step/2)]:
        wave = Perturbation(kind='pulse', amplitude_deg=amplitude, start_s=duration*.1, duration_s=duration*.5)
        data = step_response(plant, a, b, control, amplitude, duration, dt, perturbation=wave)
        np.save(path/f'response-{control}-{amplitude:g}-{dt:.8g}.npy', data)
        write_csv(path/f'input-{control}-{amplitude:g}-{dt:.8g}.csv', ['time_s', 'delta_control_deg'],
                  [(float(t), wave.value_deg(float(t))) for t in data[:, 0]])
        records.append(data)
    size = len(plant.state)
    coarse, fine, half = records
    aligned = np.column_stack([np.interp(coarse[:, 0], fine[:, 0], fine[:, i]) for i in range(1, size+1)])
    peak = np.maximum(np.max(abs(fine[:, 1:size+1]), axis=0), 1e-9)
    time_error = float(np.max(np.max(abs(coarse[:, 1:size+1]-aligned), axis=0)/peak))
    errors = [float(np.max(abs(item[:, 1:size+1]-item[:, size+1:])/plant.state_scale))
              for item in (fine, half)]
    ratio = errors[1]/errors[0] if errors[0] > 1e-12 else None
    return dict(control=control, duration_s=duration, step_s=step,
        max_step_halving_relative_change=time_error, step_passed=time_error <= .01,
        scaled_nonlinear_linear_errors=errors, amplitude_halving_error_ratio=ratio,
        amplitude_passed=ratio is None or ratio <= .35,
        ratio_limit=.35, waveform=dict(kind='pulse', start_s=duration*.1, duration_s=duration*.5,
                                      amplitudes_deg=[amplitude_deg, amplitude_deg/2]),
        interpretation='ideal quadratic ratio 0.25; <=0.35 permits numerical floor; no physical validation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--responses', action='store_true')
    parser.add_argument('--grids', type=int, nargs='+', default=[24, 48, 96])
    parser.add_argument('--inertia-hypothesis', choices=['source_as_total', 'source_as_core'], default='source_as_total')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    original = args.package.read_bytes()
    oh6 = designs.unpack(original)
    uh60 = designs.from_template('UH-60 公开部件模型（含工程估计）')
    candidates = [('synthetic', synthetic(), (0., 15.)),
                  ('oh6', candidate(oh6, 'oh6', inertia_hypothesis=args.inertia_hypothesis), (0., 20.58)),
                  ('uh60', candidate(uh60, 'uh60', inertia_hypothesis=args.inertia_hypothesis), (0., 15., 41.1556))]
    all_checks, comparison = [], []
    started = perf_counter()
    for name, design, speeds in candidates:
        for speed in speeds:
            for grid in args.grids:
                label = f'{name}-{speed:g}-n{grid}'
                item = dict(label=label, grid=grid, speed_m_s=speed)
                try:
                    plant, a, b, details = point(design, args.out/label, speed, grid)
                    item.update(status='computed', checks=details)
                    if name == 'oh6':
                        comparison.extend(compare_reference(details, speed, label))
                    if args.responses and grid == args.grids[0]:
                        item['responses'] = [response_check(plant, a, b, args.out/label, c) for c in range(4)]
                except (ValueError, np.linalg.LinAlgError) as error:
                    item.update(status='failed', error=str(error))
                all_checks.append(item)
                write_json(args.out/'checks.json', all_checks)
                print(label, item['status'], item.get('error', ''), f'{perf_counter()-started:.1f}s', flush=True)
    for speed in (0., 20.58):
        for mass_factor, accessory_factor in [(1., 1.), (.8, 1.), (1.2, 1.), (1., .5), (1., 2.)]:
            label = f'oh6-sensitivity-{speed:g}-{mass_factor:g}-{accessory_factor:g}'
            item = dict(label=label, speed_m_s=speed, mass_factor=mass_factor, accessory_factor=accessory_factor)
            try:
                model = candidate(oh6, 'oh6', mass_factor, accessory_factor, args.inertia_hypothesis)
                _, _, _, details = point(model, args.out/label, speed, args.grids[0])
                item.update(status='computed', checks=details)
                comparison.extend(compare_reference(details, speed, label))
            except (ValueError, np.linalg.LinAlgError) as error:
                item.update(status='failed', error=str(error))
            all_checks.append(item)
            write_json(args.out/'checks.json', all_checks)
            print(label, item['status'], item.get('error', ''), flush=True)
        matched = candidate(oh6, 'oh6', inertia_hypothesis=args.inertia_hypothesis)
        matched['aircraft'].pop('dynamics')
        for label, legacy_design in [(f'oh6-legacy-{speed:g}', oh6),
                                     (f'oh6-legacy-matched-inertia-{speed:g}', matched)]:
            _, _, _, details = point(legacy_design, args.out/label, speed, args.grids[0], legacy=True)
            all_checks.append(dict(label=label, status='computed', checks=details))
            comparison.extend(compare_reference(details, speed, label))
    write_json(args.out/'checks.json', all_checks)
    write_csv(args.out/'signed-derivatives.csv',
        ['variant', 'speed_m_s', 'rotor_states', 'row', 'column', 'reference', 'computed', 'signed_difference', 'signed_error_pct'], comparison)
    assert args.package.read_bytes() == original
    write_json(args.out/'manifest.json', dict(package_sha256=sha256(original).hexdigest(),
        elapsed_s=perf_counter()-started, reference_sha256=sha256(REFERENCE.read_bytes()).hexdigest(),
        engineering_use_allowed=False, source_package_unchanged=True))


if __name__ == '__main__':
    main()
