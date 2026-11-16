"""Angle editor writes physical vectors only after an explicit apply action."""
import streamlit as st
from hashlib import sha256
import json
from .mounting import mount_angles, tilt_basis, coordinate_metadata, azimuth_figure


def render_mounting(rotor, index, epoch, put_at):
    role = rotor.get('role', 'main')
    root = ['aircraft', 'rotors', index]
    physical = [rotor.get('thrust_axis_body'), rotor.get('flight', {}).get('x_reference_body'), rotor.get('rotation_sign')]
    token = sha256(json.dumps(physical).encode()).hexdigest()[:12]
    key = f'mount:{epoch}:{index}:{token}:'
    st.markdown('**安装方向、零方位与旋向**')
    st.caption('角度只在点击“应用安装角”后写入实际坐标向量。打开旧方案或查看图示不会改动安装和操纵。')
    if 'flight' not in rotor:
        st.info('旧版孤立旋翼模板继续使用历史方位缺省；安装向量在下方专业区修改。角度及零方位编辑使用新版主尾桨模板。')
        return
    try:
        angles = mount_angles(rotor)
        metadata = coordinate_metadata(rotor)
    except (ValueError, TypeError, KeyError) as error:
        st.warning(str(error) + ' 请在下方专业向量区补齐或修正。')
        return
    labels = ('主轴前倾角 / °', '主轴右倾角 / °') if role == 'main' else ('尾桨轴向前偏角 / °', '尾桨轴向上偏角 / °')
    helps = ('正推力轴向机头偏转为正；主桨为相对竖直向上方向的XZ投影角，尾桨为相对左右方向的XY投影角。',
             '主桨向机体右侧为正，尾桨向机体上方为正；这是另一正交平面的轴线投影角，不是依次叠加的Euler角。')
    with st.form(key + 'form'):
        cols = st.columns(2)
        values = [col.number_input(name, value=angles[field], min_value=-80., max_value=80., key=key + field, help=help)
                  for col, name, field, help in zip(cols, labels, ('forward_deg', 'lateral_deg'), helps)]
        side = 1
        if role == 'tail':
            side = st.selectbox('尾桨正推力侧', [1, -1], index=0 if angles['side'] == 1 else 1,
                                format_func=lambda v: '机体右侧' if v == 1 else '机体左侧', key=key + 'side',
                                help='尾桨正总距对应的正推力方向；与顺/逆时针旋向是两个独立参数。')
        zero = st.number_input('零方位绕轴偏置 / °', value=angles['zero_deg'], min_value=-180., max_value=180., key=key + 'zero',
                               help='主桨以机尾投影、尾桨以机头投影为0；绕正推力轴右手方向增加。历史机头零方位主桨回显±180°，保持原计算。')
        sign = st.selectbox('旋转方向（从正推力轴端看向轮毂）', [1, -1], index=0 if rotor['rotation_sign'] == 1 else 1,
                            format_func=lambda v: '逆时针（+1）' if v == 1 else '顺时针（−1）', key=key + 'sign',
                            help='常规向上主桨相当于从上往下看；向右尾桨相当于从机体右侧向内看。正方位角始终从局部+x朝+y，旋向只决定桨叶经过方位的次序。')
        submitted = st.form_submit_button('应用安装角')
    if submitted:
        basis = tilt_basis(role, *values, zero, side)
        put_at(root + ['thrust_axis_body'], basis[:, 2].tolist())
        put_at(root + ['flight', 'x_reference_body'], basis[:, 0].tolist())
        put_at(root + ['rotation_sign'], sign)
        st.session_state['design_epoch'] += 1
        st.rerun()
    vector = lambda v: '[' + ', '.join(f'{x:.5g}' for x in v) + ']'
    st.caption('实际正推力轴：' + vector(metadata['positive_thrust_axis_body']) + '；实际ψ=0°方向：' + vector(metadata['x_zero_body']) + '（机体系）。')
    st.caption('改变零方位会改变cos/sin操纵、挥舞和入流分量的物理方向。此编辑不自动替您重解释既有周期变距值；运行前请确认工况。')
    fig = azimuth_figure(rotor, controls_deg=[rotor['defaults']['collective_deg'], 0, 0])
    st.pyplot(fig)
    from matplotlib import pyplot as plt
    plt.close(fig)
