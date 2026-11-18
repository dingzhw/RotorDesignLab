"""Representative short responses from immutable A3 point snapshots.

All four controls are checked in the synthetic hover point separately. This
stage checks longitudinal/lateral channels in forward flight and public candidates.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.cases import write_json
from rotordesignlab.coupled_dynamics import CoupledDynamics
from rotordesignlab.trim import TrimSystem
from tools.verify_a3_aircraft import response_check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--points', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--amplitude-deg', type=float, default=.02)
    parser.add_argument('--duration-s', type=float, default=.1)
    parser.add_argument('--labels', nargs='+', help='Optional subset of the documented representative cases')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    checks = []
    started = perf_counter()
    jobs = [('synthetic-15-n24', 1), ('synthetic-15-n24', 2),
            ('oh6-0-n24', 2), ('oh6-20.58-n24', 2), ('uh60-0-n24', 2), ('uh60-15-n24', 2)]
    for label, control in jobs:
        if args.labels and label not in args.labels:
            continue
        source = args.points/label
        target = args.out/f'{label}-c{control}'
        target.mkdir()
        item = dict(label=label, control=control)
        try:
            case = json.loads((source/'trim/case.json').read_text(encoding='utf-8'))
            result = json.loads((source/'trim/result.json').read_text(encoding='utf-8'))
            if result['status'] != 'converged':
                raise ValueError(result.get('error', result['status']))
            plant = CoupledDynamics(TrimSystem(read_aircraft(source/'trim/aircraft.json'), source/'trim', case),
                                    result['diagnostics']['solved_state'], result['velocity_body_m_s'])
            matrix = np.load(source/'matrices.npz')
            np.testing.assert_array_equal(plant.state, matrix['state'])
            np.testing.assert_array_equal(plant.mass_matrix, matrix['E'])
            item.update(response_check(plant, matrix['A'], matrix['B'], target, control,
                                       duration=args.duration_s, amplitude_deg=args.amplitude_deg))
            item['status'] = 'computed'
        except (ValueError, FileNotFoundError) as error:
            item.update(status='failed', error=str(error))
        checks.append(item)
        write_json(args.out/'checks.json', checks)
        print(label, control, item['status'], f'{perf_counter()-started:.1f}s', flush=True)


if __name__ == '__main__':
    main()
