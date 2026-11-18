"""Same-input hover budget versus six-component trim; keep both methods."""
from .aircraft import read_aircraft, snapshot_aircraft
from .cases import run_case, write_json, write_csv
from .hover import VARIABLES
from .power_accounting import POWER_TERMS


def run_comparison(case, base, output):
    allowed = {'schema_version', 'model', 'analysis', 'aircraft_json', 'requested_duration_s',
               'radial_stations', 'azimuth_stations', 'environment', *VARIABLES}
    if set(case)-allowed:
        raise ValueError('悬停功率对照未识别字段：'+', '.join(sorted(set(case)-allowed)))
    source = (base/case['aircraft_json']).resolve()
    aircraft = read_aircraft(source)
    snapshot_aircraft(aircraft, source.parent, output)
    snapshot = dict(case, aircraft_json='aircraft.json')
    write_json(output/'case.json', snapshot)
    results = {}
    for analysis in ('hover_budget', 'trim'):
        child = dict(snapshot, analysis=analysis)
        if analysis == 'hover_budget':
            child.pop('azimuth_stations', None)
        else:
            child.update(speed_m_s=0., climb_m_s=0.)
        results[analysis] = run_case(child, output, output/analysis)
    complete = all(item['status'] == 'converged' for item in results.values())
    rows = []
    dependency = None
    if complete:
        budget, trim = [results[key]['summary'] for key in ('hover_budget', 'trim')]
        rows = [[label, budget[key]/1000, trim[key]/1000, (trim[key]-budget[key])/1000]
                for key, label in POWER_TERMS.items()]
        dependency = (budget['duration_margin_w'] >= 0) != (trim['duration_margin_w'] >= 0)
        write_csv(output/'power-comparison.csv', ['项目', '悬停预算_kW', '六分量配平_kW', '配平减预算_kW'], rows)
    note = ('功率可行性依赖模型假设：两方法给出相反的本次持续时间功率判定。' if dependency else
            '两方法本次功率判定同向；功率差异仍需结合假设解释。' if complete else
            '至少一种方法未收敛或超出支持范围；保留已完成结果，不比较功率优劣。')
    assumptions = []
    for key, result in results.items():
        if 'power_accounting' in result:
            for rotor in result['power_accounting']['components']:
                assumptions.append(dict(method=key, **rotor))
    warnings = [note, '预算只闭合Fz/Mz；六分量配平同时求侧力、姿态、周期变距及挥舞，机身/尾翼载荷参与。',
                '下载策略、入流分布、尖损失及预锥/挥舞须分别核对；本对照不自动改变输入或补偿系数。',
                '同一动力曲线、传动效率与附件耗功；实际连续/短时等级按给定持续时间选择。']
    result = dict(status='converged' if complete else 'failed', analysis='hover_comparison',
                  solver_status='converged' if complete else 'partial',
                  support_status='per_method', design_limits_status='per_method', evidence_status='model_estimate',
                  power_feasibility_depends_on_method=dependency, warnings=warnings,
                  methods=results, assumptions=assumptions)
    if not complete:
        result['error'] = note
    lines = ['# 同一装配的悬停功率方法对照', '', *warnings, '',
             '|项目|悬停预算 kW|六分量配平 kW|配平−预算 kW|', '|---|---:|---:|---:|']
    lines.extend(f'|{label}|{a:.6f}|{b:.6f}|{delta:.6f}|' for label, a, b, delta in rows)
    for key, item in results.items():
        name = '悬停预算' if key == 'hover_budget' else '六分量配平'
        state = '已收敛' if item['status'] == 'converged' else '失败'
        limits = '满足所给限制' if item.get('feasible') else '超出所给限制' if item.get('feasible') is False else '未评估'
        lines.extend(['', f"{name}：{state}；设计限制：{limits}；{item.get('error', '')}",
                      f'完整分项、假设、剩余力/力矩及复算输入见 `{key}/`。'])
    lines.append('本页反映两方法共同输入下的差异，不是独立试验精度或升限认证。')
    (output/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return result, snapshot
