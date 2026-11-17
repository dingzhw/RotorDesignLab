"""Installation angles and azimuth annotations use the actual rotor basis."""
import numpy as np
from .azimuth import rotor_basis
from .coordinates import selected_basis, vector3


def reference_basis(axis, role):
    reference = [-1., 0., 0.] if role == 'main' else [1., 0., 0.]
    return rotor_basis(axis, reference)


def tilt_basis(role, forward_deg, lateral_deg, zero_deg, side=1):
    """Projection angles, not sequential Euler rotations; tail lateral is UP."""
    values = np.array([forward_deg, lateral_deg, zero_deg], dtype=float)
    if not np.isfinite(values).all() or np.max(abs(values[:2])) > 80 or abs(zero_deg) > 180:
        raise ValueError('轴线偏角需在±80°、零方位偏置在±180°内。')
    if role not in ('main', 'tail') or side not in (-1, 1):
        raise ValueError('安装角需要主桨/尾桨角色及明确的尾桨推力侧。')
    forward, lateral, zero = np.deg2rad(values)
    axis = np.array([np.tan(forward), np.tan(lateral), -1.]) if role == 'main' else np.array([np.tan(forward), side, -np.tan(lateral)])
    axis /= np.linalg.norm(axis)
    base = reference_basis(axis, role)
    x = np.cos(zero) * base[:, 0] + np.sin(zero) * base[:, 1]
    return rotor_basis(axis, x)


def mount_angles(rotor):
    basis = selected_basis(rotor)
    axis = basis[:, 2]
    role = rotor.get('role', 'main')
    if role == 'main':
        if axis[2] >= -1e-8:
            raise ValueError('当前主桨正推力轴不朝上，请使用专业向量设置。')
        forward, lateral = np.rad2deg(np.arctan2(axis[:2], -axis[2]))
        side = 1
    else:
        if abs(axis[1]) < 1e-8:
            raise ValueError('当前尾桨正推力轴不指向机体左右侧，请使用专业向量设置。')
        side = 1 if axis[1] > 0 else -1
        forward, lateral = np.rad2deg(np.arctan2([axis[0], -axis[2]], abs(axis[1])))
    if max(abs(forward), abs(lateral)) > 80:
        raise ValueError('当前安装超出简化角度编辑范围，请使用专业向量设置。')
    base = reference_basis(axis, role)
    zero = np.rad2deg(np.arctan2(basis[:, 0] @ base[:, 1], basis[:, 0] @ base[:, 0]))
    return dict(forward_deg=float(forward), lateral_deg=float(lateral), zero_deg=float(zero), side=side)


def advancing_direction(rotor, flow_body):
    """Plane radial direction with maximum rotation/hub-motion tangential speed."""
    velocity = -selected_basis(rotor).T @ vector3(flow_body, '来流')
    if np.linalg.norm(velocity[:2]) < 1e-8:
        return None
    direction = rotor['rotation_sign'] * np.array([velocity[1], -velocity[0]])
    return direction / np.linalg.norm(direction)


def coordinate_metadata(rotor):
    basis = selected_basis(rotor)
    return dict(basis_rotor_to_body=basis.tolist(), x_zero_body=basis[:, 0].tolist(),
                y_90_body=basis[:, 1].tolist(), positive_thrust_axis_body=basis[:, 2].tolist(),
                rotation_sign=rotor['rotation_sign'],
                rotation_view='从正推力轴端看向桨毂',
                rotation_direction='逆时针' if rotor['rotation_sign'] == 1 else '顺时针',
                harmonic_definition='theta(psi)=theta0+theta_cos*cos(psi)+theta_sin*sin(psi); psi: +x toward +y')


def azimuth_figure(rotor, flow_body=None, controls_deg=(0., 0., 0.)):
    from matplotlib import pyplot as plt
    from .presentation import configure_chinese_plots
    configure_chinese_plots()
    basis = selected_basis(rotor)
    fig, (disk, pitch) = plt.subplots(1, 2, figsize=(10, 4.2), layout='constrained')
    angle = np.linspace(0, 2 * np.pi, 181)
    disk.plot(np.cos(angle), np.sin(angle), color='0.5')
    disk.scatter([0], [0], color='black', s=12)
    for vector, name in (([1, 0, 0], '机头'), ([-1, 0, 0], '机尾'), ([0, 1, 0], '机体右侧'),
                         ([0, -1, 0], '机体左侧'), ([0, 0, -1], '机体上方'), ([0, 0, 1], '机体下方')):
        xy = (basis.T @ vector)[:2]
        if np.linalg.norm(xy) > .3:
            xy = xy / np.linalg.norm(xy)
            disk.annotate(name, xy=.87 * xy, xytext=1.3 * xy, ha='center', va='center', fontsize=9,
                          arrowprops=dict(arrowstyle='->', color='0.5'))
    direction = None if flow_body is None else advancing_direction(rotor, flow_body)
    if direction is not None:
        for sign, name in ((1, '前行侧'), (-1, '后行侧')):
            xy = sign * .63 * direction
            disk.text(*xy, name, ha='center', va='center', color='#00688b', fontsize=10)
    else:
        note = '安装参考图：未指定来流' if flow_body is None else '无盘面内来流：不区分前/后行侧'
        disk.text(0, -.33, note, ha='center', fontsize=8)
    disk.text(.8, .12, 'ψ=0°', fontsize=9)
    disk.text(.05, .85, 'ψ=90°', fontsize=9)
    sign = rotor['rotation_sign']
    start, end = .35, .35 + sign * .7
    disk.annotate('', xy=.44 * np.array([np.cos(end), np.sin(end)]),
                  xytext=.44 * np.array([np.cos(start), np.sin(start)]),
                  arrowprops=dict(arrowstyle='->', connectionstyle=f'arc3,rad={.3 * sign}', color='#c85a17'))
    word = '逆时针' if sign == 1 else '顺时针'
    disk.set(title='从正推力轴端看向桨毂 · ' + word, xlabel='旋翼局部 x / R', ylabel='旋翼局部 y / R',
             xlim=(-1.65, 1.65), ylim=(-1.6, 1.6), aspect='equal')
    theta0, cosine, sine = controls_deg
    pitch.plot(np.rad2deg(angle), theta0 + cosine * np.cos(angle) + sine * np.sin(angle))
    pitch.set(title='总距参考站的操纵给定桨距', xlabel='几何方位角 ψ / °', ylabel='桨距角 θ / °', xlim=(0, 360))
    pitch.set_xticks([0, 90, 180, 270, 360])
    pitch.grid(alpha=.3)
    fig.suptitle('θ(ψ) = θ₀ + θcos cosψ + θsin sinψ；给定曲线尚未扣除桨距—挥舞耦合', fontsize=10)
    return fig
