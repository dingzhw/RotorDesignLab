"""Engineering atmosphere inputs with explicit legacy defaults."""
import streamlit as st
from .environment import from_case, AIR_FIELDS


def render_environment(design, task, setting, altitude=None, rotor=None):
    modern = design['settings'].get('_workspace_revision', 3) >= 6 and design['aircraft']['schema_version'] == 2
    default = 'isa' if modern or task != 'rotor' else 'custom'
    with st.expander('空气环境：高度、温差与气动参数', expanded=task == 'rotor'):
        st.caption('这是本次计算空气参数的唯一设置入口。ISA模式自动计算三项；需要逐项指定时选择自定义完整环境。主尾桨几何和翼型仍来自同一方案；切换任务后使用各任务保存的环境。')
        mode = setting(task, 'environment_mode', '环境输入方式', default, ['isa', 'custom'],
                       format_func=lambda v: '高度与ISA温差联动' if v == 'isa' else '自定义完整环境',
                       help='ISA按气压高度确定压力，再叠加温差求密度、声速和动力黏度。自定义模式逐项使用填写值；切换环境模式是物理工况改变。')
        if mode == 'isa':
            if altitude is None:
                altitude = setting(task, 'altitude_m', '飞行高度 / m', 0., min_value=0., max_value=11000., help='本页按ISA气压高度计算，范围0–11000 m。')
            offset = setting(task, 'isa_temperature_offset_k', '相对ISA温差 / °C', 0., min_value=-60., max_value=60.,
                             help='比该高度标准温度高填正、低填负；温差1°C与1 K相同。保持该气压高度的压力。')
            env = dict(mode='isa', isa_temperature_offset_k=offset)
        else:
            rotor = rotor or {}
            values = [setting(task, key, title, value, min_value=bounds[0], max_value=bounds[1], format=fmt, help=help)
                      for key, title, value, bounds, fmt, help in (
                      ('density_kg_m3', '空气密度 / (kg/m³)', 1.225, (.05, 3.), '%.7g', '直接用于叶素动压和动力学气动力。'),
                      ('speed_of_sound_m_s', '声速 / (m/s)', float(rotor.get('speed_of_sound_m_s', 340.3)), (250., 400.), '%.7g', '当地Mach数由叶素相对速度除以声速得到。'),
                      ('dynamic_viscosity_pa_s', '动力黏度 / (Pa·s)', float(rotor.get('dynamic_viscosity_pa_s', 1.7894e-5)), (1e-6, 1e-3), '%.8g', '用于当地Re计算。请填动力黏度，不是运动黏度；不能只改密度而忽略另外两项。'))]
            env = dict(mode='custom', **dict(zip(AIR_FIELDS, values)))
        result = dict(environment=env)
        if altitude is not None:
            result['altitude_m'] = altitude
        try:
            air = from_case(result)
            st.caption(f"实际密度 {air['density_kg_m3']:.7g} kg/m³；声速 {air['speed_of_sound_m_s']:.7g} m/s；动力黏度 {air['dynamic_viscosity_pa_s']:.7g} Pa·s。")
            if 'temperature_k' in air:
                st.caption(f"实际温度 {air['temperature_k']-273.15:.3g} °C；压力 {air['pressure_pa']/1000:.6g} kPa。")
        except ValueError as error:
            st.error(str(error))
        if task != 'rotor':
            st.caption('可用轴功率仍按输入的高度曲线；当前没有温度降额曲线，温差只改变空气参数。')
    return result
