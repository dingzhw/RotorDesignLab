"""Chinese preliminary-design comparison artifacts, including failed candidates."""
import numpy as np
from .design_comparison import NOTICE, CONTROL_LABELS


def render(result, rows, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .presentation import configure_chinese_plots
    configure_chinese_plots()
    names = [c['name'] for c in result['candidates']]
    x = np.arange(len(names))
    valid = [c['result']['status'] == 'converged' for c in result['candidates']]

    def values(key):
        return np.array([c['result'].get('summary', {}).get(key, np.nan) if ok else np.nan
                         for c, ok in zip(result['candidates'], valid)])

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.subplots_adjust(left=.09, right=.98, bottom=.22, top=.87, wspace=.3)
    bottom = np.zeros(len(names))
    for key, title in [('main_power_w', '主桨'), ('tail_power_w', '尾桨'),
                       ('transmission_loss_w', '传动损失'), ('accessory_power_w', '附件')]:
        height = values(key)/1000
        axes[0].bar(x, height, bottom=bottom, label=title)
        bottom += height
    margins = values('duration_margin_w')/1000
    axes[1].bar(x, margins, color=['crimson' if v < 0 else 'steelblue' for v in margins])
    axes[1].axhline(0., color='black', linewidth=.8)
    for axis, title in zip(axes, ['动力侧需用轴功率 / kW', '指定持续时间功率余量 / kW']):
        axis.set_ylabel(title)
        axis.set_xticks(x, names, rotation=12)
        axis.set_xlabel('同任务候选方案')
        axis.grid(axis='y', alpha=.2)
        for index, ok in enumerate(valid):
            if not ok:
                axis.text(index, .5, '未获得有效配平', transform=axis.get_xaxis_transform(), ha='center', rotation=90)
    axes[0].legend()
    fig.suptitle('同任务方案比较 · 模型估算（未配平候选不绘制功率）')
    for ext in ('png', 'svg'):
        fig.savefig(output/f'performance.{ext}', dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    fig.subplots_adjust(left=.09, right=.98, bottom=.12, top=.9, hspace=.5, wspace=.3)
    for axis, (control, title) in zip(axes.flat, CONTROL_LABELS.items()):
        for offset, side, label in [(-.18, 'to_lower', '到下限'), (.18, 'to_upper', '到上限')]:
            margins = [c['result'].get('control_margins_deg', {}).get(control, {}).get(side, np.nan) if ok else np.nan
                       for c, ok in zip(result['candidates'], valid)]
            axis.bar(x+offset, margins, width=.35, label=label)
        axis.set_xticks(x, names, rotation=12)
        axis.set_ylabel(title+'操纵余量 / °')
        axis.set_xlabel('同任务候选方案')
        axis.grid(axis='y', alpha=.2)
        axis.legend()
    fig.suptitle('配平操纵到限位的双向余量 · 不是飞行品质等级')
    for ext in ('png', 'svg'):
        fig.savefig(output/f'controls.{ext}', dpi=150)
    plt.close(fig)

    def clean(value):
        if value is None:
            return '—'
        if isinstance(value, float):
            return f'{value:.6g}'
        return str(value).replace('|', '/').replace('\n', ' ')

    lines = ['# 同一任务下的三方案比较', '', NOTICE, '', '## 共用任务', '',
             f"飞行质量：{result['common_mass_kg']} kg。"]
    titles = {'speed_m_s': '水平速度 / (m/s)', 'climb_m_s': '爬升率 / (m/s)', 'altitude_m': '高度 / m',
              'requested_duration_s': '维持时间 / s', 'radial_stations': '径向叶素数', 'azimuth_stations': '方位站数'}
    for key, title in titles.items():
        lines.append(f"- {title}：{result['common_task'].get(key, '采用原模型缺省')}。")
    from .environment import from_case
    try:
        air = from_case(result['common_task'])
        lines.append(f"- 实际空气密度 {air['density_kg_m3']:.6g} kg/m³，声速 {air['speed_of_sound_m_s']:.6g} m/s，动力黏度 {air['dynamic_viscosity_pa_s']:.6g} Pa·s。")
    except ValueError:
        lines.append('- 空气环境未通过输入检查，参见各点失败原因。')
    groups = [('功率与状态', ['方案', '求解', '支持范围', '设计限制', '主桨气动轴功率_kW', '尾桨气动轴功率_kW',
                            '主桨传动损失_kW', '尾桨传动损失_kW', '附件耗功_kW', '动力侧需用轴功率_kW',
                            '额定口径', '所用可用功率_kW', '本次持续时间功率余量_kW']),
              ('设计参数', ['方案', '飞行质量_kg', '重心X_m', '主桨半径_m', '主桨转速_rpm', '主桨实度',
                          '主桨盘载_N_m2', '主桨旋转桨尖Mach', '主桨局部最大Mach', '尾桨半径_m', '尾桨转速_rpm',
                          '尾桨纵向力臂_m', '主桨传动效率', '尾桨传动效率']),
              ('配平与操纵余量', ['方案', '滚转角_deg', '俯仰角_deg']+
               [title+suffix for title in CONTROL_LABELS.values() for suffix in ('_deg', '到下限_deg', '到上限_deg')])]
    for title, columns in groups:
        lines.extend(['', '## '+title, '', '|'+ '|'.join(columns)+'|', '|'+ '|'.join(['---']*len(columns))+'|'])
        for row in rows:
            lines.append('|'+ '|'.join(clean(row.get(key)) for key in columns)+'|')
    lines.extend(['', '## 来源、假设与失败记录'])
    for entry in result['candidates']:
        lines.extend(['', '### '+clean(entry['name']), '', '候选来源：'+clean(entry['change']['provenance']),
                      '几何规则：'+entry['geometry_rule']+'；'+entry['mass_inertia_update']+'。'])
        for key, source in entry.get('sources', {}).items():
            lines.append({'aircraft':'原装配来源', 'mass_properties':'质量惯量来源',
                          'rotors':'旋翼来源', 'powerplant':'动力来源'}[key]+'：'+clean(source))
        answer = entry['result']
        if answer.get('error'):
            lines.append('失败：'+clean(answer['error']))
        if 'power_accounting' in answer:
            ledger = answer['power_accounting']
            rating = '短时' if ledger['rating'] == 'short_time' else '连续'
            lines.append(f"动力按{rating}额定 {ledger['selected_available_w']/1000:.6g} kW判断；短时限时 {ledger['short_time_duration_s']:g} s。")
            lines.append('配平入流为稳态三状态模型、无附加尖损失；残余下载策略：'+answer['download_model']['strategy']+'。')
        lines.append(f"实际机型/几何/工况与诊断：`{entry['directory']}/`。")
    lines.extend(['', '数值收敛、支持范围、设计限制及验证依据分别判断；失败不记为零功率。',
                  '表内实度按实际桨根切除后的桨叶平面面积/名义桨盘面积定义；局部最大Mach不等同于旋转桨尖Mach。',
                  '本轮固定飞行质量用于比较气动/动力趋势；尚未评估尺寸变化后的结构重量、制造、成本与完整任务性能。',
                  'batch.json可整体搬移复算；各candidate/run/case.json可独立复算；不修改模块库或基准装配。'])
    (output/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
