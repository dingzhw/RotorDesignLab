"""Bounded rotor-level diagnostic; never replaces the aircraft A/B matrices.

Usage: python -m tools.diagnose_hub_transfer --package public-example.rdl --out NEW_DIRECTORY
Mass sweeps are mathematical sensitivities, not measured blade masses.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy.optimize import root

from rotordesignlab import designs
from rotordesignlab.airframe import body_to_ned
from rotordesignlab.cases import run_case, write_csv, write_json
from rotordesignlab.hub_loads import BladeMass, blade_motion, blade_on_hub
from rotordesignlab.trim import TrimSystem


def diagnose(package, out):
    original = package.read_bytes()
    out.mkdir(parents=True, exist_ok=False)
    design = designs.unpack(original)
    aircraft_path = designs.materialize(deepcopy(design), out / 'input')
    records = []
    checks = []
    for speed in (0., 20.58):
        case = dict(schema_version=3, model='helicopter', analysis='trim',
                    aircraft_json=aircraft_path.name, speed_m_s=speed, climb_m_s=0.,
                    altitude_m=0., requested_duration_s=180., azimuth_stations=36,
                    radial_stations=40, environment={'mode': 'isa', 'isa_temperature_offset_k': 0.})
        target = out / f'trim-{speed:g}'
        trim = run_case(case, aircraft_path.parent, target)
        if trim['status'] != 'converged':
            raise ValueError(f'诊断基点配平失败：{trim.get("error", trim["status"])}')
        # Reuse the actual normalized/snapshotted model (including applied grid).
        from rotordesignlab.aircraft import read_aircraft
        system = TrimSystem(read_aircraft(target / 'aircraft.json'), target, case)
        state = np.array(trim['diagnostics']['solved_state'])
        model = system.rotors['main']
        cfg = model.config
        if model.fixed:
            raise ValueError('此诊断需要具有一阶、二阶质量矩的铰接主旋翼。')
        basis = system.bases['main']
        velocity = np.array(trim['velocity_body_m_s'])
        gravity = basis.T @ body_to_ned(*state[4:6]).T @ np.array([0., 0., 9.80665])
        arm = np.array(system.selected['main']['position_m']) - system.aircraft['mass_properties']['cg_m']
        first, second = cfg['first_mass_moment_kg_m'], cfg['inertia_kg_m2']
        minimum_mass = first**2 / second
        for inflow_mode in ('frozen', 'quasisteady'):
            for mass_factor in (1., 1.5, 2.):
                mass = BladeMass(minimum_mass * mass_factor, first, second,
                                 model.rotor.radius - cfg['hinge_offset_m'])

                def loads_at(body_rate):
                    hub_velocity = basis.T @ (velocity + np.cross(body_rate, arm))
                    shaft_rate = basis.T @ body_rate
                    seed = state[6:12].copy()
                    def equation(unknown):
                        trial = unknown if inflow_mode == 'quasisteady' else np.r_[seed[:3], unknown]
                        residual = model.evaluate(trial, state[:3], hub_velocity, gravity, body_rates=shaft_rate)[0]
                        return residual if inflow_mode == 'quasisteady' else residual[3:]
                    fit = root(equation, seed if inflow_mode == 'quasisteady' else seed[3:], tol=1e-10)
                    if not np.isfinite(fit.x).all() or np.max(abs(equation(fit.x))) > 1e-7:
                        raise ValueError('诊断扰动点的入流/挥舞未收敛。')
                    solved = fit.x if inflow_mode == 'quasisteady' else np.r_[seed[:3], fit.x]
                    _, data, _ = model.evaluate(solved, state[:3], hub_velocity, gravity, strict=True,
                                                body_rates=shaft_rate, require_equilibrium=inflow_mode == 'quasisteady')
                    motion = blade_motion(model.kernel.psi, data['beta'], data['beta_dot'], data['beta_ddot'],
                                          model.rotor.omega, model.kernel.rotation_sign, cfg['hinge_offset_m'],
                                          body_rates=shaft_rate)
                    force = data['element_force'].sum(axis=1)
                    moment = np.cross(data['position'], data['element_force']).sum(axis=1)
                    transmitted = blade_on_hub(motion, mass, force, moment, gravity=gravity)
                    average = lambda array: basis @ (model.rotor.blades * array.mean(axis=0))
                    return np.r_[average(force), average(moment),
                                 average(transmitted['force']), average(transmitted['moment'])]

                matrices = []
                for step in (1e-4, 5e-5):
                    derivatives = []
                    for index in range(3):
                        offset = np.eye(3)[index] * step
                        derivatives.append((loads_at(offset) - loads_at(-offset)) / (2*step))
                    matrices.append(np.column_stack(derivatives))
                # Near-zero derivatives use an absolute 1e-4 N or N m per rad/s floor.
                scale = np.maximum(abs(matrices[1]), 1e-4)
                change = float(np.max(abs(matrices[0] - matrices[1]) / scale))
                checks.append(dict(speed_m_s=speed, inflow=inflow_mode, mass_factor=mass_factor,
                                   derivative_halving_change=change, passed=change <= .02))
                if change > .02:
                    raise ValueError('桨毂诊断导数步长检查超过2%。')
                for i, load in enumerate(('aero_Fx', 'aero_Fy', 'aero_Fz', 'aero_Mx', 'aero_My', 'aero_Mz',
                                          'hub_Fx', 'hub_Fy', 'hub_Fz', 'hub_Mx', 'hub_My', 'hub_Mz')):
                    for j, rate in enumerate(('p', 'q', 'r')):
                        records.append(dict(speed_m_s=speed, inflow=inflow_mode, mass_factor=mass_factor,
                                            blade_mass_kg=mass.mass_kg, load=load, rate=rate,
                                            derivative=float(matrices[1][i, j])))
        print(f'{speed:g} m/s: rotor transfer diagnostic completed', flush=True)
    write_csv(out / 'derivatives.csv', list(records[0]), [list(row.values()) for row in records])
    write_json(out / 'checks.json', dict(
        package_sha256=sha256(original).hexdigest(), checks=checks,
        scope='Main rotor only; body-axis forces and shaft-origin moments; frozen vs quasi-steady inflow; prescribed zero hub/angular acceleration.',
        mass_assumption='m1²/I is only a lower bound; 1/1.5/2 times that bound are sensitivity cases, not measured blade mass.',
        engineering_use_allowed=False,
        missing=['main blade mass provenance', 'tail blade mass moments', 'whole-aircraft vs nonrotating mass/inertia partition',
                 'implicit acceleration/flap coupling', 'slow harmonic-amplitude derivatives', 'full aircraft signed derivative comparison'],
    ))
    if package.read_bytes() != original:
        raise RuntimeError('原始方案包在检查中被外部修改。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    diagnose(args.package, args.out)
