"""Two-second A3 checks with unchanged models, matrices and fixed thresholds.

Runs production RK4; writes every completed/failed trajectory before continuing.
Public parameter candidates retain their diagnostic-only mass assumptions.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from rotordesignlab.cases import write_json, write_csv
from rotordesignlab.dynamics import step_response, ResponseDomainError
from rotordesignlab.perturbation import Perturbation
from tools.diagnose_a3_amplitude import load_point, error_metrics, integrate


def confirm_long(points, reference, output):
    """Independent DOP853 confirmation when tiny model errors need more scrutiny."""
    original = json.loads((reference/'checks.json').read_text(encoding='utf-8'))
    checks = []
    for item in original:
        plant, a, b = load_point(points/item['label'])
        errors = []
        comparisons = []
        for name, amplitude in [('fine', .02), ('half', .01)]:
            saved = np.load(reference/item['label']/(name+'.npy'))
            wave = Perturbation(kind=item['waveform'], amplitude_deg=amplitude,
                                start_s=item['start_s'], duration_s=item['width_s'])
            history, calls = integrate(plant, a, b, amplitude, duration=2., waveform=wave,
                                       max_step=.00125, rtol=1e-11, atol=1e-13,
                                       sample_times=saved[:, 0])
            np.save(output/f'{item["label"]}-{name}.npy', history)
            errors.append(error_metrics(history, plant))
            size = len(plant.state)
            peaks = np.maximum(np.max(abs(history[:, 1:size+1]), axis=0), 1e-9)
            difference = float(np.max(np.max(abs(history[:, 1:size+1]-saved[:, 1:size+1]), axis=0)/peaks))
            comparisons.append(dict(amplitude_deg=amplitude, nfev=calls,
                                    production_relative_difference=difference,
                                    passed=difference <= .01))
            write_json(output/f'{item["label"]}-{name}.json', dict(errors=errors, comparisons=comparisons))
            print(item['label'], name, calls, flush=True)
        ratio = errors[1]['scaled_peak_error']/errors[0]['scaled_peak_error']
        checks.append(dict(label=item['label'], errors=errors, comparisons=comparisons,
                           amplitude_halving_error_ratio=ratio, amplitude_passed=ratio <= .35,
                           ratio_limit=.35, rtol=1e-11, atol_scaled=1e-13, max_step_s=.00125,
                           interpretation='independent numerical diagnostic; retains original RK4 failure'))
        write_json(output/'checks.json', checks)


def report(points, folder):
    """Add named state exports and Chinese plots without replacing trajectories."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from rotordesignlab.presentation import configure_chinese_plots, STATE_LABELS
    configure_chinese_plots()
    checks = json.loads((folder/'checks.json').read_text(encoding='utf-8'))
    for item in checks:
        plant, _, _ = load_point(points/item['label'])
        item['state_names'] = plant.state_names
        item['state_units'] = plant.state_units
        item['state_scale'] = plant.state_scale.tolist()
        if item['status'] != 'computed':
            continue
        history = np.load(folder/item['label']/'fine.npy')
        size = len(plant.state)
        headers = ['时间_s']+[f'{kind}_{name}_{unit}' for kind in ('非线性增量', '线性增量')
                              for name, unit in zip(plant.state_names, plant.state_units)]
        write_csv(folder/item['label']/'fine-states.csv', headers, history.tolist())
        fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout='constrained')
        for axis, name in zip(axes.flat, ['p', 'q', 'main_betas_rate']):
            index = plant.state_names.index(name)
            axis.plot(history[:, 0], history[:, 1+index], label='非线性')
            axis.plot(history[:, 0], history[:, 1+size+index], '--', label='线性')
            axis.set_ylabel(STATE_LABELS[name]+' / ('+plant.state_units[index]+')')
            axis.legend()
        error = (history[:, 1:size+1]-history[:, size+1:])/plant.state_scale
        axes[1, 1].plot(history[:, 0], np.max(abs(error), axis=1))
        axes[1, 1].set_ylabel('全状态归一化误差最大值')
        for axis in axes.flat:
            axis.set_xlabel('时间 / s')
            axis.grid(alpha=.25)
        title = '合成机 15 m/s' if item['label'].startswith('synthetic') else 'OH-6A 诊断候选 20.58 m/s'
        waveform = {'pulse': '平滑脉冲', 'doublet': '双脉冲', 'step': '阶跃'}[item['waveform']]
        fig.suptitle(title+' · 两秒'+waveform+'响应（模型诊断）')
        fig.savefig(folder/item['label']/'response.png', dpi=160)
        plt.close(fig)
    write_json(folder/'checks.json', checks)


def compare_histories(coarse, fine, half, plant):
    size = len(plant.state)
    aligned = np.column_stack([np.interp(coarse[:, 0], fine[:, 0], fine[:, i])
                               for i in range(1, size+1)])
    peaks = np.maximum(np.max(abs(fine[:, 1:size+1]), axis=0), 1e-9)
    changes = np.max(abs(coarse[:, 1:size+1]-aligned), axis=0)/peaks
    errors = [error_metrics(history, plant) for history in (fine, half)]
    full_error, half_error = [item['scaled_peak_error'] for item in errors]
    ratio = half_error/full_error if full_error > 1e-12 else None
    return dict(max_step_halving_relative_change=float(max(changes)),
                step_peak_state=plant.state_names[int(np.argmax(changes))],
                step_passed=bool(max(changes) <= .01), errors=errors,
                amplitude_halving_error_ratio=ratio,
                amplitude_passed=ratio is None or ratio <= .35,
                ratio_limit=.35, step_limit=.01, component_peak_floor_si=1e-9,
                numerical_error_floor_scaled=1e-12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--points', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--labels', nargs='+', default=['synthetic-15-n24', 'oh6-20.58-n24'])
    parser.add_argument('--kind', choices=['pulse', 'doublet', 'step'], default='pulse')
    parser.add_argument('--report-only', action='store_true',
                        help='Add named CSV/plots to an existing completed run; keep raw trajectories')
    parser.add_argument('--confirm-run', type=Path,
                        help='Independently integrate an existing run into a new output directory')
    args = parser.parse_args()
    if args.report_only:
        report(args.points, args.out)
        return
    args.out.mkdir(parents=True, exist_ok=False)
    if args.confirm_run:
        confirm_long(args.points, args.confirm_run, args.out)
        return
    checks = []
    start = perf_counter()
    for label in args.labels:
        plant, a, b = load_point(args.points/label)
        folder = args.out/label
        folder.mkdir()
        item = dict(label=label, control_index=2, duration_s=2., waveform=args.kind,
                    start_s=.2, width_s=.5, original_equilibrium_scaled_rhs=float(np.max(abs(
                        plant.rhs(plant.state, plant.controls)/plant.state_scale))),
                    matrix_sha256=sha256((args.points/label/'matrices.npz').read_bytes()).hexdigest(),
                    runs=[], interpretation='numerical diagnostic; original model and stored A/B; no drift subtraction')
        histories = []
        for name, amplitude, dt in [('coarse', .02, .001), ('fine', .02, .0005), ('half', .01, .0005)]:
            wave = Perturbation(kind=args.kind, amplitude_deg=amplitude, start_s=.2, duration_s=.5)
            record = dict(name=name, amplitude_deg=amplitude, step_s=dt)
            try:
                history = step_response(plant, a, b, 2, amplitude, 2., dt, perturbation=wave)
                record['status'] = 'computed'
            except ResponseDomainError as error:
                history = error.history
                record.update(status='failed', error=str(error))
            np.save(folder/f'{name}.npy', history)
            write_csv(folder/f'{name}-input.csv', ['time_s', 'delta_control_deg'],
                      [(float(t), wave.value_deg(float(t))) for t in history[:, 0]])
            record.update(last_time_s=float(history[-1, 0]) if len(history) else None,
                          rows=len(history), elapsed_s=perf_counter()-start)
            item['runs'].append(record)
            histories.append(history)
            write_json(folder/'checks.json', item)
            print(label, name, record['status'], f'{perf_counter()-start:.1f}s', flush=True)
        if all(run['status'] == 'computed' for run in item['runs']):
            item.update(status='computed', **compare_histories(*histories, plant))
        else:
            item.update(status='failed', step_passed=False, amplitude_passed=False)
        checks.append(item)
        write_json(args.out/'checks.json', checks)
    write_json(args.out/'manifest.json', dict(elapsed_s=perf_counter()-start,
               model='harmonic_hub_v1; unchanged frozen A3 candidates', control='index 2 periodic pitch',
               protocol='2 s; pulse/doublet width .5 s; start .2 s; .02/.01 degree; h .001/.0005 s'))


if __name__ == '__main__':
    main()
