"""Bounded interpolation experiment on frozen A3 inputs; no polar fitting."""
import argparse
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from rotordesignlab.cases import write_json, read_case, read_rotor, THREE_BLADE
from rotordesignlab.rotor import solve
from tools.verify_a3_aircraft import point, response_check


def snapshot_design(folder, method):
    aircraft = json.loads((folder/'trim/aircraft.json').read_text(encoding='utf-8'))
    assets = {}
    for rotor in aircraft['rotors']:
        for key in ('geometry_csv', 'polar_csv', 'polar_json'):
            if key in rotor:
                name = rotor[key]
                assets[name] = (folder/'trim'/name).read_text(encoding='utf-8')
        if 'polar_csv' in rotor:
            rotor['polar_interpolation'] = method
    return dict(format_version=1, aircraft=aircraft, assets=assets, settings={})


def summarize(folder, long_folder, target):
    """Publish compact public evidence; all trajectories remain in runs/."""
    if target.exists():
        raise ValueError('摘要已存在，请指定新文件；历史检查保留。')
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    hashes = {}
    for path in sorted((folder/'points').rglob('*')):
        if path.is_file() and path.suffix in ('.json', '.csv', '.npz'):
            hashes[str(path.relative_to(folder))] = sha256(path.read_bytes()).hexdigest()
    rotor = read_rotor(read_case(THREE_BLADE), THREE_BLADE.parent)[0]
    axial = []
    for speed in (0., 25.):
        for method in ('linear_v1', 'pchip_alpha_v1'):
            totals = solve(replace(rotor, axial_speed=speed, polar_interpolation=method))[0]
            axial.append(dict(speed_m_s=speed, method=method, summary=totals))
    write_json(target, dict(
        scope='CSV alpha C1 interior candidate; same nodes; no physical calibration',
        limitations=['OH6 source_as_core remains diagnostic, not verified mass accounting',
                     'No C1 claim at alpha endpoints or angle wrapping; no multidimensional table change',
                     'Only control index 2 and smooth pulses checked; old doublet failure retained'],
        short_checks=read(folder/'checks.json'), trends=read(folder/'trends.json'),
        two_second=read(long_folder/'checks.json'), fixed_collective_axial=axial,
        input_and_matrix_sha256=hashes,
        runtime=dict(interpolation=read(folder/'manifest.json'), two_second=read(long_folder/'manifest.json'))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--points', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--summarize', type=Path, help='Write new compact evidence from existing results')
    parser.add_argument('--two-second', type=Path)
    args = parser.parse_args()
    if args.summarize:
        if args.two_second is None:
            parser.error('--summarize requires --two-second')
        summarize(args.out, args.two_second, args.summarize)
        return
    args.out.mkdir(parents=True, exist_ok=False)
    checks = []
    start = perf_counter()
    for label, speed in [('synthetic-15-n24', 15.), ('oh6-20.58-n24', 20.58)]:
        original = json.loads((args.points/label/'checks.json').read_text(encoding='utf-8'))
        design = snapshot_design(args.points/label, 'pchip_alpha_v1')
        plant, a, b, details = point(design, args.out/'points'/label, speed, 24)
        item = dict(label=label, derivative_check=details['derivative_check'],
                    equilibrium_rhs_max=details['equilibrium_rhs_max'],
                    old_summary=original['summary'], new_summary=details['summary'], responses=[])
        for sign in (1., -1.):
            folder = args.out/label/('positive' if sign > 0 else 'negative')
            folder.mkdir(parents=True)
            item['responses'].append(response_check(plant, a, b, folder, 2, duration=.1, amplitude_deg=sign*.02))
            write_json(args.out/'checks.json', checks+[item])
        checks.append(item)
        print(label, [r['amplitude_halving_error_ratio'] for r in item['responses']], flush=True)
    trends = []
    for label, high in [('synthetic-15-n24', 15.), ('oh6-20.58-n24', 20.58)]:
        for method in ('linear_v1', 'pchip_alpha_v1'):
            design = snapshot_design(args.points/label, method)
            for speed in (0., 10., high):
                name = f'{label}-{method}-{speed:g}'
                _, _, _, details = point(deepcopy(design), args.out/'trends'/name, speed, 24)
                trends.append(dict(label=label, method=method, speed_m_s=speed, summary=details['summary']))
                write_json(args.out/'trends.json', trends)
    write_json(args.out/'manifest.json', dict(elapsed_s=perf_counter()-start,
               method='pchip_alpha_v1; original nodes; no smoothing/fitting parameter',
               limits='CSV alpha C1 interior only; original support domain; no new wake physics'))


if __name__ == '__main__':
    main()
