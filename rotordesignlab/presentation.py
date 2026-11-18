"""Chinese presentation labels, independent of calculation field names."""
AXIS_LABELS = {
    'rpm':'旋翼转速 / rpm', 'collective_deg':'总距 / °',
    'axial_speed_m_s':'轴向来流速度 / (m/s)', 'density_kg_m3':'空气密度 / (kg/m³)',
    'flow_x_m_s':'X方向来流 / (m/s)', 'flow_y_m_s':'Y方向来流 / (m/s)', 'flow_z_m_s':'Z方向来流 / (m/s)',
    'motion_forward_m_s':'水平前向运动速度 / (m/s)', 'motion_right_m_s':'水平右向运动速度 / (m/s)',
    'motion_climb_m_s':'上升速度 / (m/s)',
    'target_thrust_n':'目标拉力 / N', 'mass_kg':'整机质量 / kg', 'altitude_m':'高度 / m',
    'main_radius_m':'主旋翼半径 / m', 'main_rpm':'主旋翼转速 / rpm',
    'tail_radius_m':'尾桨半径 / m', 'tail_rpm':'尾桨转速 / rpm', 'tail_arm_m':'尾桨力臂 / m',
    'speed_m_s':'水平速度 / (m/s)', 'climb_m_s':'爬升率 / (m/s)', 'cg_x_m':'重心纵向位置 / m',
    'main_cos_deg':'主桨 cos 周期变距 / °', 'main_sin_deg':'主桨 sin 周期变距 / °',
}
CONTROL_LABELS = {'main_collective':'主桨总距', 'main_cos':'主桨 cos 周期变距',
                  'main_sin':'主桨 sin 周期变距', 'tail_collective':'尾桨总距'}
STATE_LABELS = {'u':'纵向速度 u', 'v':'侧向速度 v', 'w':'垂向速度 w',
                'p':'滚转角速度 p', 'q':'俯仰角速度 q', 'r':'偏航角速度 r'}
for role, title in [('main', '主桨'), ('tail', '尾桨')]:
    for suffix, component in [('0', '锥度'), ('c', 'cos挥舞'), ('s', 'sin挥舞')]:
        STATE_LABELS[role+'_beta'+suffix] = title+component+'幅值 β'+suffix
        STATE_LABELS[role+'_beta'+suffix+'_rate'] = title+component+'幅值变化率'


def configure_chinese_plots():
    """Use an installed CJK font and embed SVG glyphs for portable exports."""
    import matplotlib
    from matplotlib import font_manager
    candidates=['Microsoft YaHei','SimHei','Noto Sans CJK SC','Source Han Sans SC','WenQuanYi Zen Hei','SimSun']
    for family in candidates:
        try:font_manager.findfont(font_manager.FontProperties(family=family),fallback_to_default=False)
        except ValueError:continue
        matplotlib.rcParams.update({'font.family':[family,'DejaVu Sans'],'axes.unicode_minus':False,'svg.fonttype':'path'})
        return family
    raise RuntimeError('未找到中文绘图字体。请准备微软雅黑、黑体或思源黑体后重试；计算输入与已有结果仍保留。')
