"""Explicit candidate inputs persisted with the existing design/settings package."""
import streamlit as st

LABEL = '同任务三方案（功率与配平）'


def candidate_form(aircraft, setting, namespace):
    main = next(r for r in aircraft['rotors'] if r['role'] == 'main')
    tail = next(r for r in aircraft['rotors'] if r['role'] == 'tail')
    cg = aircraft['mass_properties']['cg_m'][0]
    original = dict(main_radius_m=float(main['radius_m']), main_rpm=float(main['defaults']['rpm']),
                    tail_radius_m=float(tail['radius_m']), tail_arm_m=float(cg-tail['position_m'][0]), cg_x_m=float(cg))
    labels = {'main_radius_m': '主桨半径 / m', 'main_rpm': '主桨转速 / rpm',
              'tail_radius_m': '尾桨半径 / m', 'tail_arm_m': '尾桨纵向力臂 / m', 'cg_x_m': '重心X / m'}
    help_text = {'main_radius_m': '改变半径时r/R站位随半径缩放，弦长规则在下方选择；不自动估算结构质量。',
                 'main_rpm': '主桨给定转速。已声明传动速比时尾桨随之联动；独立转速安装保持尾桨原值。',
                 'tail_radius_m': '改变尾桨半径，使用同一弦长/实度保持规则。',
                 'tail_arm_m': '重心到尾桨桨毂的纵向距离，向机尾为正；有效偏航推力臂还受安装方向影响。',
                 'cg_x_m': '机体系X向前，相对统一原点。页面按所填尾桨力臂重新确定尾桨X位置；主桨及其他部件安装位置保持。重心改变不自动更新惯量。'}
    st.info('三方案共用当前飞行质量、速度、高度、空气环境、维持时间和六分量配平模型。'
            '默认候选仅用于探索尺寸/转速趋势；几何变化后的结构质量与惯量须另核。')
    variants = []
    for index, name in enumerate(('基准方案', '主桨加大5%', '主桨降速5%')):
        prefix = f'candidate-{index}-'
        with st.expander(f'候选{index+1}：设计参数与来源', expanded=index == 0):
            title = setting(namespace, prefix+'name', f'候选{index+1}名称', name,
                            help='填写可区分的名称。结果按输入顺序展示，不按优劣自动排序。')
            values = {}
            for key, baseline in original.items():
                default = baseline
                if index == 1 and key == 'main_radius_m':
                    default *= 1.05
                if index == 2 and key == 'main_rpm':
                    default *= .95
                values[key] = setting(namespace, prefix+key, f'候选{index+1} '+labels[key], default,
                                      format='%.6f', help=help_text[key])
            rule = setting(namespace, prefix+'geometry_rule', f'候选{index+1} 半径变化规则',
                           'preserve_chord', options=['preserve_chord', 'preserve_solidity'],
                           format_func=lambda v: {'preserve_chord':'保持实际弦长与扭转', 'preserve_solidity':'保持实度与扭转'}[v],
                           help='保持实度时弦长随半径同比缩放。两种规则均不自动更新质量矩/惯量；必须在报告中说明。')
            source = setting(namespace, prefix+'provenance', f'候选{index+1} 来源与估算说明',
                             '沿用基准装配来源；本候选为总体设计敏感性假设，质量矩和惯量未重新估算。',
                             help='说明设计变化来自实测、公开资料还是工程假设；旧模板的出处不会自动证明新参数有效。')
            overrides = {k:v for k,v in values.items() if v != original[k]}
            if 'cg_x_m' in overrides:
                overrides['tail_arm_m'] = values['tail_arm_m']
            variants.append(dict(name=title, overrides=overrides,
                                 geometry_rule=rule, provenance=source))
    return lambda: dict(schema_version=1, kind='helicopter_design_comparison', variants=variants)
