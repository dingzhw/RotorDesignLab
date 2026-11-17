"""Rigid line-blade Newton--Euler loads in the thrust-positive rotor frame.

This kernel takes prescribed motion, not an equilibrium assumption. Mass moments
are per blade, measured from the flap hinge. It returns blade-on-hub loads;
these must be paired with NON-blade mass properties in a fuselage equation.
See docs/hub-loads.md before integrating into an aircraft model.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class BladeMass:
    mass_kg: float
    first_moment_kg_m: float
    second_moment_kg_m2: float
    length_m: float

    def __post_init__(self):
        m, first, second, length = (
            self.mass_kg, self.first_moment_kg_m,
            self.second_moment_kg_m2, self.length_m,
        )
        if not np.isfinite([m, first, second, length]).all() or min(m, first, second, length) <= 0:
            raise ValueError('桨叶质量、铰外一阶矩、二阶矩和长度须为有限正数。')
        tolerance = 1e-12
        if (first > m * length * (1 + tolerance)
                or second > length * first * (1 + tolerance)
                or first**2 > m * second * (1 + tolerance)):
            raise ValueError('桨叶质量矩不满足铰外非负质量分布的矩约束。')


def blade_motion(psi, beta, beta_dot, beta_ddot, omega, rotation_sign, hinge_offset_m,
                 *, body_rates=(0., 0., 0.), hub_acceleration=(0., 0., 0.),
                 body_acceleration=(0., 0., 0.)):
    """x(s)=origin+s*span; inertial a(s)=acceleration0+s*acceleration1.

    s is distance from hinge (m). omega is positive, psi_dot=sign*omega.
    beta_dot/ddot are TOTAL prescribed flap derivatives, not automatically
    limited to azimuth harmonics. Hub acceleration is inertial translational
    acceleration expressed in rotor axes; body_acceleration is angular (rad/s²).
    Rotor shaft speed is constant. No chordwise mass, lead-lag or elastic DOF.
    """
    psi, beta, beta_dot, beta_ddot = np.broadcast_arrays(
        *[np.asarray(v, dtype=float) for v in (psi, beta, beta_dot, beta_ddot)]
    )
    if psi.ndim != 1 or not psi.size or not np.isfinite([psi, beta, beta_dot, beta_ddot]).all():
        raise ValueError('桨叶运动须为等长、非空的一维有限数组。')
    if (rotation_sign not in (-1, 1) or type(rotation_sign) is not int
            or not np.isfinite([omega, hinge_offset_m]).all() or omega <= 0 or hinge_offset_m < 0):
        raise ValueError('转速须为正、旋向为整数±1、铰偏置须非负。')
    rate, hub_acc, angular_acc = [np.asarray(v, dtype=float) for v in
                                 (body_rates, hub_acceleration, body_acceleration)]
    if any(v.shape != (3,) or not np.isfinite(v).all() for v in (rate, hub_acc, angular_acc)):
        raise ValueError('角速度、轮毂加速度、角加速度均须为三个有限数。')
    er = np.column_stack((np.cos(psi), np.sin(psi), np.zeros_like(psi)))
    epsi = np.column_stack((-np.sin(psi), np.cos(psi), np.zeros_like(psi)))
    span = np.cos(beta)[:, None] * er
    span[:, 2] = np.sin(beta)
    normal = -np.sin(beta)[:, None] * er
    normal[:, 2] = np.cos(beta)
    origin = hinge_offset_m * er
    spin = rotation_sign * omega
    velocity0 = spin * hinge_offset_m * epsi
    velocity1 = spin * np.cos(beta)[:, None] * epsi + beta_dot[:, None] * normal
    relative_acceleration0 = -omega**2 * origin
    relative_acceleration1 = (
        -omega**2 * np.cos(beta)[:, None] * er
        - 2 * spin * (np.sin(beta) * beta_dot)[:, None] * epsi
        + beta_ddot[:, None] * normal - beta_dot[:, None]**2 * span
    )
    acceleration0 = (hub_acc + np.cross(angular_acc, origin)
                     + np.cross(rate, np.cross(rate, origin))
                     + 2 * np.cross(rate, velocity0) + relative_acceleration0)
    acceleration1 = (np.cross(angular_acc, span) + np.cross(rate, np.cross(rate, span))
                     + 2 * np.cross(rate, velocity1) + relative_acceleration1)
    return dict(origin=origin, span=span, normal=normal, flap_axis=-epsi,
                velocity0=velocity0, velocity1=velocity1,
                acceleration0=acceleration0, acceleration1=acceleration1)


def flap_inertial_moment(motion, first_moment, second_moment):
    """Generalized inertial moment about the positive-beta hinge axis (N m)."""
    weighted_acceleration = (first_moment * motion['acceleration0']
                             + second_moment * motion['acceleration1'])
    return np.einsum('ij,ij->i', motion['normal'], weighted_acceleration)


def _skew(vectors):
    out = np.zeros((len(vectors), 3, 3))
    x, y, z = vectors.T
    out[:, 0, 1], out[:, 0, 2] = -z, y
    out[:, 1, 0], out[:, 1, 2] = z, -x
    out[:, 2, 0], out[:, 2, 1] = -y, x
    return out


def blade_on_hub(motion, mass, aerodynamic_force, aerodynamic_moment, *, gravity=(0., 0., 0.)):
    """Per-azimuth single-blade transmitted wrench, about the shaft origin.

    F_h = F_a + m*g - integral(a dm)
    M_h = M_a + integral(x dm) cross g - integral(x cross a dm)

    Aerodynamic moments must use the same origin. Springs/dampers are already
    internal to this balance: do NOT add them again. Their hinge-axis moment
    appears when the supplied beta acceleration satisfies the flap equation.
    """
    origin, span = motion['origin'], motion['span']
    a0, a1 = motion['acceleration0'], motion['acceleration1']
    m, first, second = mass.mass_kg, mass.first_moment_kg_m, mass.second_moment_kg_m2
    force, moment = [np.asarray(v, dtype=float) for v in (aerodynamic_force, aerodynamic_moment)]
    gravity = np.asarray(gravity, dtype=float)
    if (force.shape != origin.shape or moment.shape != origin.shape
            or gravity.shape != (3,) or not np.isfinite(force).all()
            or not np.isfinite(moment).all() or not np.isfinite(gravity).all()):
        raise ValueError('每方位单片桨叶气动力/气动力矩须为N×3有限数组，重力须为三维向量。')
    mass_position = m * origin + first * span
    inertial_force = m * a0 + first * a1
    inertial_moment = (m * np.cross(origin, a0)
                       + first * (np.cross(origin, a1) + np.cross(span, a0))
                       + second * np.cross(span, a1))
    outer = lambda a, b: np.einsum('ni,nj->nij', a, b)
    position_second = (m * outer(origin, origin)
                       + first * (outer(origin, span) + outer(span, origin))
                       + second * outer(span, span))
    inertia = np.trace(position_second, axis1=1, axis2=2)[:, None, None] * np.eye(3) - position_second
    mass_matrix = np.zeros((len(origin), 6, 6))
    mass_matrix[:, :3, :3] = m * np.eye(3)
    mass_matrix[:, :3, 3:] = -_skew(mass_position)
    mass_matrix[:, 3:, :3] = _skew(mass_position)
    mass_matrix[:, 3:, 3:] = inertia
    return dict(force=force + m * gravity - inertial_force,
                moment=moment + np.cross(mass_position, gravity) - inertial_moment,
                inertial_force=inertial_force, inertial_moment=inertial_moment,
                gravity_force=np.broadcast_to(m * gravity, force.shape).copy(),
                gravity_moment=np.cross(mass_position, gravity), mass_matrix=mass_matrix)
