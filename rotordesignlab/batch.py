"""Portable Cartesian operating-point sweeps with per-point diagnostics."""

from copy import deepcopy
from itertools import product
from math import isfinite
import os
from pathlib import Path
from tempfile import gettempdir

from . import __version__
from .aircraft import read_aircraft, snapshot_aircraft
from .cases import read_case, run_case, write_csv, write_json
from .coordinates import MOTION_AXES, FLOW_AXES, canonical_spatial_case, scan_velocity

from .presentation import AXIS_LABELS as DISPLAY_AXIS_LABELS, configure_chinese_plots

# These keys also define the supported sweep inputs; labels from other analyses
# must not expand the isolated-rotor input contract.
AXIS_LABELS = {key: DISPLAY_AXIS_LABELS[key] for key in
               ('rpm', 'collective_deg', 'axial_speed_m_s', 'density_kg_m3', 'target_thrust_n',
                *FLOW_AXES, *MOTION_AXES)}


def plot_performance(rows, axes, output, model='aircraft_rotor'):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(gettempdir()) / 'rotordesignlab-matplotlib'))
    try:
        import matplotlib
    except ImportError as error:
        raise RuntimeError('批量绘图需要 Matplotlib，请按 requirements-win64-py314.txt 准备依赖。') from error
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    configure_chinese_plots()
    x_key, *groups = list(axes)
    group_key = groups[0] if groups else None
    group_values = axes[group_key] if group_key else [None]
    fig, panels = plt.subplots(1, 3, figsize=(14, 4.5), layout='constrained')
    colors = plt.get_cmap('tab10')
    for index, group in enumerate(group_values):
        selected = sorted((row for row in rows if group_key is None or row[group_key] == group),
                          key=lambda row: row[x_key])
        label = f'{AXIS_LABELS[group_key]} = {group:g}' if group_key else '计算工况'
        x = [row[x_key] for row in selected]
        for panel, key, title, factor in zip(panels, ('thrust_n', 'torque_nm', 'power_w'),
                                            ('拉力 / N', '轴扭矩 / (N·m)', '轴功率 / kW'),
                                            (1, 1, 0.001)):
            # NaN retains failed-point gaps instead of bridging across them.
            y = [row.get(key, float('nan')) * factor for row in selected]
            panel.plot(x, y, 'o-', color=colors(index % 10), label=label, markersize=3)
            bad = [i for i, row in enumerate(selected) if row['status'] == 'converged' and not row['feasible']]
            if bad:
                panel.scatter(np.asarray(x)[bad], np.asarray(y)[bad], marker='x', color='crimson', zorder=4)
            panel.set(xlabel=AXIS_LABELS[x_key], ylabel=title)
            panel.grid(alpha=0.25)
    panels[0].legend(fontsize=8)
    failures = sum(row['status'] != 'converged' for row in rows)
    violations = sum(row['status'] == 'converged' and not row['feasible'] for row in rows)
    title = '孤立旋翼三方向性能（模型估算）' if model == 'spatial_rotor' else '孤立旋翼轴流性能'
    fig.suptitle(f'{title}｜{len(rows)} 个工况｜{failures} 个失败｜'
                 f'{violations} 个超过限制（红色叉号）', fontsize=11)
    fig.savefig(output / 'performance.png', dpi=160)
    fig.savefig(output / 'performance.svg')
    plt.close(fig)


def run_batch(spec, base, output):
    if isinstance(spec, dict) and spec.get('kind') == 'rotor_module_sweep':
        from .module_batch import run_batch as run_module_batch
        return run_module_batch(spec, base, output)
    if isinstance(spec,dict) and spec.get('kind')=='helicopter_trim_sweep':
        from .trim_batch import run_trim_batch
        return run_trim_batch(spec,Path(base),Path(output))
    if isinstance(spec, dict) and spec.get('kind') in ('helicopter_sweep', 'helicopter_comparison'):
        from .hover_batch import run_hover_batch
        return run_hover_batch(spec, base, output)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('输出目录已有文件，请指定新的空目录。')
    with (output / 'run.lock').open('x'):
        pass
    result = dict(schema_version=1, solver_version=__version__, model='rotor_batch',
                  status='failed', warnings=[], summary={})
    saved = deepcopy(spec)
    try:
        if (not isinstance(spec, dict) or type(spec.get('schema_version')) is not int or
            spec['schema_version'] != 1 or spec.get('kind') != 'rotor_sweep' or
            set(spec) - {'schema_version', 'kind', 'case_json', 'axes'}):
            raise ValueError('批量文件需为版本 1 的 rotor_sweep，包含 case_json 和 axes。')
        if not isinstance(spec.get('case_json'), str):
            raise ValueError('case_json 必须为工况文件路径。')
        source = (Path(base) / spec['case_json']).resolve()
        case = read_case(source)
        if not isinstance(case, dict) or case.get('model') not in ('aircraft_rotor','spatial_rotor') or case.get('schema_version') != 2:
            raise ValueError('旋翼批量功能使用版本2的 aircraft_rotor 或 spatial_rotor 工况。')
        axes = spec.get('axes')
        if not isinstance(axes, dict) or not 1 <= len(axes) <= 2 or set(axes) - set(AXIS_LABELS):
            raise ValueError('axes 需含 1 至 2 个受支持的工况变量。')
        if case['model'] == 'spatial_rotor':
            if 'axial_speed_m_s' in axes:
                raise ValueError('三方向旋翼扫描请使用运动速度或机体系来流分量。')
            case = canonical_spatial_case(case)
            if set(axes) & set(MOTION_AXES) and set(axes) & set(FLOW_AXES):
                raise ValueError('同一批次不能混合运动速度与机体系来流扫描轴。')
        if case['model'] == 'aircraft_rotor' and set(axes) & set((*FLOW_AXES, *MOTION_AXES)):
            raise ValueError('运动速度和X/Y/Z来流扫描需要三方向旋翼模型。')
        if 'environment' in case and 'density_kg_m3' in axes and (not isinstance(case['environment'], dict) or case['environment'].get('mode') != 'custom'):
            raise ValueError('ISA环境的密度由高度与温差确定；密度扫描需选择完整自定义环境。')
        count = 1
        for key, values in axes.items():
            if (not isinstance(values, list) or not values or
                any(type(value) not in (int, float) or not isfinite(value) for value in values)):
                raise ValueError(f'{key} 扫描值必须是有限数值列表。')
            if len(values) != len(set(values)):
                raise ValueError(f'{key} 扫描值不能重复。')
            count *= len(values)
        if len(axes) == 2 and len(list(axes.values())[1]) > 12:
            raise ValueError('性能图第二个变量最多 12 条曲线。')
        if count > 1000:
            raise ValueError('单批最多 1000 个工况。')
        target = case.get('target')
        if target is not None and not isinstance(target, dict):
            raise ValueError('target 必须为对象。')
        if target and target.get('solve_for') in axes:
            raise ValueError('扫描变量不能同时作为反求变量。')
        if 'target_thrust_n' in axes and not target:
            raise ValueError('target_thrust_n 扫描需要反求工况。')
        if not isinstance(case.get('aircraft_json'), str):
            raise ValueError('工况缺少 aircraft_json。')
        aircraft_path = source.parent / case['aircraft_json']
        inputs = output / 'inputs'
        inputs.mkdir()
        snapshot_aircraft(read_aircraft(aircraft_path), aircraft_path.parent, inputs)
        case['aircraft_json'] = 'aircraft.json'
        write_json(inputs / 'case.json', case)
        saved['case_json'] = 'inputs/case.json'
        write_json(output / 'batch.json', saved)
        rows = []
        for index, point in enumerate(product(*axes.values())):
            current = deepcopy(case)
            values = dict(zip(axes, point))
            if case['model'] == 'spatial_rotor':
                current = scan_velocity(current, values)
            for key, value in values.items():
                if key == 'target_thrust_n':
                    current['target']['thrust_n'] = value
                elif key == 'density_kg_m3' and 'environment' in current:
                    current['environment']['density_kg_m3'] = value
                elif key in (*FLOW_AXES, *MOTION_AXES):
                    continue
                else:
                    current[key] = value
            name = f'case-{index:04d}'
            answer = run_case(current, inputs, output / name)
            row = dict(case_id=name, **values, status=answer['status'], feasible=answer.get('feasible', False),
                       error=answer.get('error', ''))
            for key in ('solver_status', 'support_status', 'design_limits_status', 'evidence_status'):
                row[key] = answer[key]
            if answer['status'] == 'converged':
                summary = answer['summary']
                row.update({key: summary[key] for key in ('thrust_n', 'torque_nm', 'power_w')})
                row.update(solved_rpm=summary['rpm'], solved_collective_deg=summary['collective_deg'])
                row['target_relative_error'] = answer.get('target_solution', {}).get('relative_thrust_error', '')
                for key in ('power_w', 'torque_nm'):
                    row[key.replace('_w', '_margin_w').replace('_nm', '_margin_nm')] = answer['installation']['margins'].get(key, '')
            rows.append(row)
        headers = ['case_id', *axes, 'status', 'feasible', 'thrust_n', 'torque_nm', 'power_w',
                   'solved_rpm', 'solved_collective_deg', 'target_relative_error',
                   'power_margin_w', 'torque_margin_nm', 'solver_status', 'support_status',
                   'design_limits_status', 'evidence_status', 'error']
        write_csv(output / 'performance.csv', headers, ([row.get(key, '') for key in headers] for row in rows))
        failed = sum(row['status'] != 'converged' for row in rows)
        result['summary'] = dict(total=len(rows), converged=len(rows)-failed, failed=failed,
                                 limit_violations=sum(row['status'] == 'converged' and not row['feasible'] for row in rows))
        plot_performance(rows, axes, output, model=case['model'])
        result['analysis_model'] = case['model']
        result['status'] = 'converged' if not failed else ('partial' if failed < len(rows) else 'failed')
        result.update(solver_status=result['status'], support_status='per_point',
                      design_limits_status='per_point', evidence_status='model_estimate')
        result['warnings'] = ['失败点保留逐点诊断；图中断线表示求解失败，红叉表示超过给定功率或扭矩限制。']
        if case['model'] == 'spatial_rotor':
            from .model_scope import SPATIAL_SCOPE
            result['model_maturity'] = SPATIAL_SCOPE
            result['warnings'].append(SPATIAL_SCOPE)
        if failed:
            result['error'] = f'{failed} 个工况求解失败，详见 performance.csv 和逐点 result.json。'
    except (ValueError, OSError, RuntimeError) as error:
        result['error'] = str(error)
    finally:
        try:
            write_json(output / 'batch.json', saved)
        except (ValueError, TypeError):
            result['error'] = '批量输入包含不可保存的数值或类型。'
            result['status'] = 'failed'
        write_json(output / 'result.json', result)
        (output / 'run.lock').unlink()
    return result
