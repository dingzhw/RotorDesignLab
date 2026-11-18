"""Bounded B-package attribution using original public/synthetic inputs."""
import argparse
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import numpy as np
from rotordesignlab import designs, assembly
from rotordesignlab.cases import read_case, run_case, write_json
from rotordesignlab.trim import TrimSystem
from rotordesignlab.rotor import solve
from rotordesignlab.inverse import solve_target
from rotordesignlab.steady_rotor import SteadyRotor


def controlled_rotors(folder, budget):
    aircraft = read_case(folder/'aircraft.json')
    case = dict(read_case(folder/'case.json'), speed_m_s=0., climb_m_s=0., azimuth_stations=36)
    system = TrimSystem(aircraft, folder, case)
    rows = []
    for role in ('main', 'tail'):
        base = replace(system.rotors[role].rotor, precone_deg=0.,
                       collective_deg=budget['summary'][role+'_collective_deg'])
        target = budget['summary'][role+'_thrust_n']
        for inflow, tip in [('annular', 'prandtl'), ('annular', 'none'), ('uniform', 'none')]:
            rotor = replace(base, inflow_model=inflow, tip_loss=tip)
            same_pitch = solve(rotor)[0]
            solved, (same_thrust, _, _), diagnostic = solve_target(
                rotor, dict(solve_for='collective_deg', thrust_n=target), system.selected[role]['limits'])
            item = dict(role=role, inflow=inflow, tip_loss=tip, same_pitch=same_pitch,
                        same_thrust=same_thrust, inverse=diagnostic)
            if inflow == 'uniform':
                fixed = dict(mode='fixed', hinge_offset_m=0., precone_deg=0., max_flap_deg=15.)
                matches = []
                for model, summary in [(rotor, same_pitch), (solved, same_thrust)]:
                    _, loads, _ = SteadyRotor(model, fixed).solve(
                        np.deg2rad([model.collective_deg, 0., 0.]), [0., 0., 0.])
                    delta = [float(loads['force'][2]/summary['thrust_n']-1),
                             float(loads['power']/summary['power_w']-1)]
                    matches.append(delta)
                item['fixed_pp_relative_T_P_differences'] = matches
                assert np.max(np.abs(matches)) <= 1e-6
            rows.append(item)
    return dict(scope='同几何/转速/环境/总距或拉力；两核均固定零预锥、零铰偏置、零周期变距、相同名义桨盘面积。非原整机工况。', rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oh6-package', type=Path)
    parser.add_argument('--inputs', type=Path, help='公开冻结输入目录，含synthetic/aircraft.json与oh6/aircraft.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.inputs is None and args.oh6_package is None:
        parser.error('需要--inputs或--oh6-package')
    args.out.mkdir(parents=True, exist_ok=False)
    if args.inputs is not None:
        sources = []
        for name in ('synthetic', 'oh6'):
            base = args.inputs/name
            aircraft = read_case(base/'aircraft.json')
            assets = {r[key]: (base/r[key]).read_text(encoding='utf-8')
                      for r in aircraft['rotors'] for key in ('geometry_csv', 'polar_csv', 'polar_json') if key in r}
            sources.append((name, dict(format_version=1, aircraft=aircraft, assets=assets, settings={},
                                       template='B包冻结公开/合成输入；含工程估算，非试验认证')))
    else:
        sources = [('synthetic', designs.from_template('200 kg 合成无人直升机')),
                   ('oh6', designs.unpack(args.oh6_package.read_bytes()))]
    report = []
    for name, original in sources:
        original = assembly.from_legacy(original)
        source = designs.materialize(original, args.out/name/'inputs')
        common = dict(schema_version=3, model='helicopter', altitude_m=0., requested_duration_s=600.,
                      radial_stations=80, azimuth_stations=36)
        compare = run_case(dict(common, aircraft_json=str(source.resolve()), analysis='hover_comparison'),
                           Path('.'), args.out/name/'comparison')
        assert compare['status'] == 'converged', compare
        budget, trim = [compare['methods'][key] for key in ('hover_budget', 'trim')]
        stages = [('original_budget', budget)]
        # Ordered conditional attribution, not independent additive causal effects.
        for label in ('no_tip', 'uniform', 'trim_same_download'):
            variant = deepcopy(original)
            # These are explicit diagnostic copies; reassemble their edited aircraft
            # to avoid an inconsistent saved module snapshot.
            variant['format_version'] = 1
            variant.pop('assembly', None)
            for rotor in variant['aircraft']['rotors']:
                rotor['tip_loss'] = 'none'
                if label in ('uniform', 'trim_same_download'):
                    rotor['inflow_model'] = 'uniform'
            analysis = 'hover_budget'
            case = dict(common)
            if label == 'trim_same_download':
                variant['aircraft']['trim']['download_policy'] = 'legacy_fraction'
                analysis = 'trim'
                case.update(speed_m_s=0., climb_m_s=0.)
            else:
                case.pop('azimuth_stations')
            path = designs.materialize(variant, args.out/name/label/'inputs')
            result = run_case(dict(case, analysis=analysis, aircraft_json=str(path.resolve())),
                              Path('.'), args.out/name/label/'output')
            assert result['status'] == 'converged', result
            stages.append((label, result))
        stages.append(('original_trim', trim))
        attribution = []
        for (left, before), (right, after) in zip(stages[:-1], stages[1:]):
            keys = ('main_power_w', 'tail_power_w', 'transmission_loss_w', 'accessory_power_w', 'required_power_w')
            attribution.append(dict(change=left+' -> '+right,
                                    delta_w={k: after['summary'][k]-before['summary'][k] for k in keys}))
        checks = controlled_rotors(args.out/name/'comparison'/'hover_budget', budget)
        item = dict(name=name, assembly_sha256=assembly.digest(original['assembly']),
                    methods=compare, attribution=attribution, controlled_rotors=checks,
                    stage_summaries={key: result['summary'] for key, result in stages})
        if name == 'oh6':
            # Original expert load case; short rating is a design input, not a flight-test truth.
            limit = run_case(dict(common, aircraft_json=str(source.resolve()), analysis='hover_comparison',
                                 mass_kg=1185.2, requested_duration_s=180.),
                             Path('.'), args.out/name/'rating-disagreement')
            item['rating_disagreement'] = limit
        report.append(item)
        write_json(args.out/'checks.json', report)
        print(name, [(x['change'], x['delta_w']['required_power_w']) for x in attribution], flush=True)


if __name__ == '__main__':
    main()
