"""Two editable views of one physical velocity; switching converts values."""
import numpy as np
import streamlit as st
from .coordinates import (MOTION_AXES, FLOW_AXES, motion_to_flow, flow_to_motion,
                          canonical_spatial_case, selected_basis)


def render_velocity(design, epoch, setting):
    task = 'rotor'
    cfg = design['settings'].get(task, {})
    default_view = 'motion' if design['settings'].get('_workspace_revision', 3) >= 5 else 'flow'
    view_key = f'a:{epoch}:rotor:velocity_view'
    prefix = f'a:{epoch}:rotor:'

    def change_view():
        saved = design['settings'].setdefault(task, {})
        before = saved.get('velocity_view', default_view)
        after = st.session_state[view_key]
        angles = [saved.get('attitude_roll_deg', 0.), saved.get('attitude_pitch_deg', 0.)]
        try:
            if before == 'motion':
                converted = motion_to_flow([saved.get(k, 0.) for k in MOTION_AXES], angles)
                keys = FLOW_AXES
            else:
                converted = flow_to_motion([saved.get(k, 0.) for k in FLOW_AXES], angles)
                keys = MOTION_AXES
            for key, value in zip(keys, converted):
                saved[key] = float(value)
                st.session_state[prefix + key] = float(value)
            saved['velocity_view'] = after
            st.session_state.pop(prefix + 'switch_error', None)
        except ValueError as error:
            st.session_state[view_key] = before
            st.session_state[prefix + 'switch_error'] = str(error)

    view = cfg.get('velocity_view', default_view)
    view = st.selectbox('速度输入视角', ['motion', 'flow'], index=0 if view == 'motion' else 1,
                        format_func=lambda v: {'motion': '飞行器运动速度', 'flow': '空气相对桨毂 XYZ'}[v],
                        key=view_key, on_change=change_view,
                        help='切换时转换已填数值，保持同一物理速度。运动视角相对静止空气；XYZ视角使用机体系，均不含诱导速度。')
    if prefix + 'switch_error' in st.session_state:
        st.error(st.session_state[prefix + 'switch_error'])
    if view == 'motion':
        labels = ('水平前向速度 / (m/s)', '水平右向速度 / (m/s)', '上升速度 / (m/s)')
        helps = ('沿机头水平投影向前为正，后退填负值。', '地平面内向机头右侧为正，向左填负值。',
                 '相对地平面向上为正，下降填负值；下降是否可算由所选旋翼正贯流范围判断。')
        keys = MOTION_AXES
    else:
        labels = tuple('来流 ' + axis + ' 分量 / (m/s)' for axis in 'XYZ')
        helps = ('空气相对桨毂，沿机体系X向前为正；水平前飞20 m/s时填−20。',
                 '沿机体系Y向右为正；水平向右运动时此分量为负。',
                 '沿机体系Z向下为正；水平姿态上升3 m/s时填+3。')
        keys = FLOW_AXES
    values = []
    for column, key, label, explanation in zip(st.columns(3), keys, labels, helps):
        with column:
            values.append(setting(task, key, label, 0., min_value=-150., max_value=150., help=explanation))
    with st.expander('姿态与速度参考系'):
        roll = setting(task, 'attitude_roll_deg', '机体滚转角 / °', 0., min_value=-180., max_value=180.,
                       help='机体绕X轴右手转动，右侧向下为正；同时用于运动速度转换和重力方向。')
        pitch = setting(task, 'attitude_pitch_deg', '机体俯仰角 / °', 0., min_value=-89., max_value=89.,
                        help='机头上仰为正。运动视角采用机头水平投影方向，不是倾斜后的机体X轴方向。')
        st.caption('运动速度相对静止空气，按“水平前、水平右、向上”填写；空气来流采用机体系X前、Y右、Z下。姿态不是旋翼安装角。')
    return dict(attitude_deg=[roll, pitch], **{('motion_m_s' if view == 'motion' else 'flow_body_m_s'): values})


def inflow_preview(case, rotor, rpm):
    try:
        physical = canonical_spatial_case(case)
        flow = np.asarray(physical['flow_body_m_s'])
        angles = physical.get('attitude_deg', [0., 0.])
        motion = flow_to_motion(flow, angles)
        velocity = -selected_basis(rotor).T @ flow
        tip = float(rpm) * np.pi / 30 * rotor['radius_m']
        if not np.isfinite(tip) or tip <= 0:
            raise ValueError('推进比回显需要有效的正转速和旋翼半径。')
        mu = np.linalg.norm(velocity[:2]) / tip
        vector = lambda values: '[' + ', '.join(f'{v:.5g}' for v in values) + ']'
        st.caption(f'实际运动〔水平前、水平右、上〕：{vector(motion)} m/s；滚转/俯仰：{vector(angles)}°。')
        st.caption(f'实际空气来流〔机体系X、Y、Z〕：{vector(flow)} m/s；合速度 {np.linalg.norm(flow):.5g} m/s。')
        st.caption(f'所选旋翼盘面内推进比 μ={mu:.5g}；沿正推力轴的桨毂运动分量 {velocity[2]:.5g} m/s（不含诱导）。反求转速时以求得转速为准。')
        if mu > .25 or velocity[2] < -1e-9:
            st.warning('当前参考工况超出μ≤0.25或正贯流范围；最终支持状态以求解诊断为准。')
    except (ValueError, TypeError, KeyError) as error:
        st.warning('暂不能回显推进比：' + str(error))
