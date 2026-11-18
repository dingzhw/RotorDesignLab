"""Portable independent rotor sweeps, using exactly the single-point entry."""
from copy import deepcopy
from itertools import product
import math
from pathlib import Path

from . import __version__, rotor_module
from .cases import read_case, write_json, write_csv, run_case

AXES = {'collective_deg': '总距 / °', 'rpm': '转速 / (r/min)',
        'altitude_m': '气压高度 / m', 'flow_x': '局部空气速度 x / (m/s)',
        'flow_y': '局部空气速度 y / (m/s)', 'flow_z': '局部空气速度 z / (m/s)'}


def validate_spec(spec):
    if (spec.get('schema_version') != 1 or spec.get('kind') != 'rotor_module_sweep' or
            set(spec) != {'schema_version', 'kind', 'case_json', 'axes'}):
        raise ValueError('独立旋翼扫描需要版本1、case_json及axes。')
    axes = spec['axes']
    if not isinstance(axes, dict) or not 1 <= len(axes) <= 2 or set(axes) - AXES.keys():
        raise ValueError('请选择1至2个受支持的扫描参数。')
    count = 1
    for values in axes.values():
        if not isinstance(values, list) or not values or len(values) > 100:
            raise ValueError('每个扫描轴需要1至100个数值。')
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
            raise ValueError('扫描值必须为有限数。')
        count *= len(values)
    if count > 100:
        raise ValueError('一次扫描最多100点。')


def run_batch(spec, base, output):
    base, output = Path(base), Path(output)
    validate_spec(spec)
    axes = spec['axes']
    source = (base / spec['case_json']).resolve()
    case = read_case(source)
    if case.get('model') != 'rotor_module' or case.get('schema_version') != 4:
        raise ValueError('扫描须读取独立旋翼工况。')
    if 'target' in case and case['target'].get('solve_for') in axes:
        raise ValueError('反求的待求量不能同时作为扫描变量。')
    if 'altitude_m' in axes and case.get('environment', {}).get('mode', 'isa') != 'isa':
        raise ValueError('高度扫描需要ISA联动环境。')
    module, assets = rotor_module.load(source.parent / case['module_file'])
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('请使用新的空输出目录。')
    rotor_module.save(module, assets, output / 'module.rdlr')
    case['module_file'] = 'module.rdlr'
    write_json(output / 'case.json', case)
    write_json(output / 'batch.json', dict(spec, case_json='case.json'))
    rows = []
    for index, values in enumerate(product(*axes.values())):
        point = deepcopy(case)
        settings = dict(zip(axes, values))
        for key, value in settings.items():
            if key.startswith('flow_'):
                point['flow_rotor_m_s']['xyz'.index(key[-1])] = value
            else:
                point[key] = value
        result = run_case(point, output, output / f'point-{index:03d}')
        row = dict(settings, point=index, status=result['status'],
                   error=result.get('error', ''), design_limits_status=result.get('design_limits_status', 'not_evaluated'),
                   support_status=result.get('support_status', 'not_evaluated'), evidence_status='model_estimate')
        row.update({k: result.get('summary', {}).get(k) for k in ('thrust_n', 'torque_nm', 'power_w')})
        rows.append(row)
    write_csv(output / 'performance.csv', list(rows[0]), [list(row.values()) for row in rows])
    answer = dict(status='converged' if all(r['status'] == 'converged' for r in rows) else 'failed',
                  model='rotor_module_sweep', solver_version=__version__, rows=rows,
                  summary={'points': len(rows), 'converged_points': sum(r['status'] == 'converged' for r in rows)},
                  warnings=['各点保存独立工况与结果；失败点不绘成有效性能曲线。'], evidence_status='model_estimate')
    plot(rows, axes, output)
    write_json(output / 'result.json', answer)
    return answer


def plot(rows, axes, output):
    import matplotlib.pyplot as plt
    from .presentation import configure_chinese_plots
    configure_chinese_plots()
    x_key = next(iter(axes))
    group_key = list(axes)[1] if len(axes) == 2 else None
    groups = axes[group_key] if group_key else [None]
    fig, panels = plt.subplots(1, 3, figsize=(13, 4), layout='constrained')
    for group in groups:
        selected = sorted([r for r in rows if group_key is None or r[group_key] == group], key=lambda r: r[x_key])
        for panel, key, label, factor in zip(panels, ('thrust_n', 'torque_nm', 'power_w'),
                                           ('拉力 / N', '轴扭矩 / (N·m)', '轴功率 / kW'), (1, 1, .001)):
            y = [r[key]*factor if r['status'] == 'converged' else math.nan for r in selected]
            panel.plot([r[x_key] for r in selected], y, 'o-',
                       label=f'{AXES[group_key]} = {group:g}' if group_key else '计算结果')
            panel.set_xlabel(AXES[x_key])
            panel.set_ylabel(label)
            panel.grid(True, alpha=.25)
            panel.legend()
    for extension in ('png', 'svg'):
        fig.savefig(output / ('performance.' + extension), dpi=140)
    plt.close(fig)
