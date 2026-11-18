"""Rig orientation and flow views; canonical solver vectors stay in rotor axes."""
import numpy as np
import pandas as pd
import streamlit as st
from . import rotor_trial as trial


def render(hidden):
    from .module_ui import current, key, vector
    draft = current()
    case = draft['case']
    pose = draft.get('trial')
    mode, _, _ = trial.effective_flap(draft)
    with st.expander('试验姿态与坐标示意'):
        if pose is None:
            st.info('此方案只记录了局部向量，未记录机头参考方向。继续使用桨盘坐标可原样复算。需要前右下运动输入时，请明确设置试验姿态后应用。')
        st.caption('参考系B：X前、Y右、Z下。零姿态桨盘系：X后、Y右、Z上（推力轴）。姿态依次按固定轴滚转、俯仰、偏航旋转；不要求整机位置。')
        with st.form(key('trial-pose')):
            angles = (pose or {}).get('angles_deg', [0., 0., 0.])
            values = [st.number_input(title, value=float(value), key=key('pose-'+str(i)),
                                      help='右手正向，单位度；允许竖直桨盘。矩阵为Rz(偏航)Ry(俯仰)Rx(滚转)。')
                      for i, (title, value) in enumerate(zip(['试验滚转 / °', '试验俯仰 / °', '试验偏航 / °'], angles))]
            if mode == 'hinged':
                g = st.number_input('重力加速度 g / (m/s²)', value=float((pose or {}).get('gravity_m_s2', np.linalg.norm(case['gravity_rotor_m_s2']))),
                                    min_value=0., max_value=30., help='地面常用9.80665；0仅用于无重力对照。程序按试验姿态投影到桨盘。')
            else:
                g = float((pose or {}).get('gravity_m_s2', np.linalg.norm(case['gravity_rotor_m_s2'])))
            st.caption('应用姿态保持桨盘来流数值；改变其在参考系中的方向，并按姿态更新局部重力。旧方案原包不覆盖。')
            if st.form_submit_button('应用试验姿态'):
                draft['trial'] = dict(schema_version=1, angles_deg=values, gravity_m_s2=g)
                case['gravity_rotor_m_s2'] = trial.gravity(values, g).tolist()
                st.session_state['module-epoch'] += 1
                st.rerun()
        if pose:
            matrix = trial.basis(pose['angles_deg'])
            st.dataframe(pd.DataFrame(matrix, index=['参考X前', '参考Y右', '参考Z下'], columns=['桨盘X零方位', '桨盘Y', '桨盘Z推力轴']))
            # Arrows share the very same basis used by input conversion.
            import matplotlib.pyplot as plt
            from .presentation import configure_chinese_plots
            configure_chinese_plots()
            fig = plt.figure(figsize=(4, 3))
            ax = fig.add_subplot(projection='3d')
            for i, color in enumerate(('r', 'g', 'b')):
                axis = matrix[:, i]
                ax.quiver(0, 0, 0, *axis, color=color)
                ax.text(*axis, ['桨盘X', '桨盘Y', '桨盘Z'][i])
            ax.set(xlim=(-1, 1), ylim=(-1, 1), zlim=(1, -1), xlabel='前', ylabel='右', zlabel='下')
            st.pyplot(fig)
            plt.close(fig)
    flow_scan = any(name.startswith('flow_') for name in hidden)
    choices = ['空气相对桨毂速度（桨盘坐标）']
    if pose and not flow_scan:
        choices.insert(0, '运动速度（前、右、下）')
    view = st.radio('速度填写方式', choices, horizontal=True, key=key('trial-flow-view'),
                    help='运动速度相对于空气，不是地速。来流是不含诱导速度的空气相对桨毂速度；转换只在入口执行一次。')
    motion = view.startswith('运动')
    values = trial.flow_to_motion(case['flow_rotor_m_s'], pose['angles_deg']) if motion else np.asarray(case['flow_rotor_m_s'])
    names = ['向前速度 / (m/s)', '向右速度 / (m/s)', '向下速度 / (m/s)'] if motion else ['桨盘X来流 / (m/s)', '桨盘Y来流 / (m/s)', '轴向Z来流 / (m/s)']
    for i, col in enumerate(st.columns(3)):
        if 'flow_'+'xyz'[i] in hidden:
            col.caption(names[i]+'由扫描给定')
            continue
        widget = key('trial-speed/'+str(motion)+'/'+str(i))
        def changed(i=i, widget=widget):
            current_values = trial.flow_to_motion(case['flow_rotor_m_s'], pose['angles_deg']) if motion else np.array(case['flow_rotor_m_s'])
            current_values[i] = st.session_state[widget]
            case['flow_rotor_m_s'] = (trial.motion_to_flow(current_values, pose['angles_deg']) if motion else current_values).tolist()
            for j in range(3):
                st.session_state.pop(key('trial-speed/'+str(not motion)+'/'+str(j)), None)
        col.number_input(names[i], value=float(values[i]), key=widget, on_change=changed,
                         help='正值沿所示正方向，负值反向。标准姿态下向前10对应桨盘X来流+10，向右3对应Y来流−3；下降仍受模型范围限制。')
    st.caption('实际桨盘来流 [X, Y, Z] = '+str(case['flow_rotor_m_s'])+' m/s；Z沿正推力轴。')
    if case['flow_rotor_m_s'][2] > 1e-9:
        st.warning('当前为反贯流/下降侧输入，现有求解器不支持；不会自动改成爬升。')
    if mode == 'hinged':
        if pose:
            st.caption('实际局部重力 = '+str(case['gravity_rotor_m_s2'])+' m/s²；在试验姿态中设置g。')
        else:
            with st.expander('历史局部重力（高级）'):
                vector(case, 'gravity_rotor_m_s2', '局部重力 / (m/s²)', [0., 0., -9.80665], 'case', '保留原局部向量；零向量为无重力对照，不推测试验姿态。')
