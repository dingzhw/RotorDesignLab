"""Blade-element loads and the axial steady limit of Pitt–Peters inflow."""

from dataclasses import dataclass
from math import pi

import numpy as np
from scipy.optimize import brentq


class SolverError(ValueError):
    """The requested operating point could not be solved."""


@dataclass(frozen=True)
class Rotor:
    geometry: np.ndarray
    polar: np.ndarray
    blades: int
    radius: float
    omega: float
    axial_speed: float
    density: float
    collective_deg: float
    pitch_reference: float
    stations: int

    def grid(self):
        root = self.geometry[0, 0] * self.radius
        edges = np.linspace(root, self.radius, self.stations + 1)
        radius = (edges[1:] + edges[:-1]) / 2
        chord = np.interp(radius / self.radius, self.geometry[:, 0], self.geometry[:, 1])
        twist = np.interp(radius / self.radius, self.geometry[:, 0], self.geometry[:, 2])
        reference = np.interp(self.pitch_reference, self.geometry[:, 0], self.geometry[:, 2])
        pitch = np.deg2rad(self.collective_deg + twist - reference)
        return radius, np.diff(edges), chord, pitch


def axial_loads(rotor, grid, induced_speed):
    radius, widths, chord, pitch = grid
    shape = (rotor.blades, len(radius))
    tangential = np.broadcast_to(rotor.omega * radius, shape)
    axial = rotor.axial_speed + induced_speed
    inflow_angle = np.arctan2(axial, tangential)
    alpha = np.rad2deg(pitch - inflow_angle)
    angles, lift, drag = rotor.polar.T
    cl = np.interp(alpha, angles, lift)
    cd = np.interp(alpha, angles, drag)
    pressure_area = 0.5 * rotor.density * (tangential**2 + axial**2) * chord * widths
    lift_force, drag_force = pressure_area * cl, pressure_area * cd
    thrust = lift_force * np.cos(inflow_angle) - drag_force * np.sin(inflow_angle)
    tangential_force = lift_force * np.sin(inflow_angle) + drag_force * np.cos(inflow_angle)
    return thrust, tangential_force, alpha


def solve(rotor):
    grid = rotor.grid()
    radius, widths, chord, pitch = grid
    momentum_factor = 2 * rotor.density * pi * rotor.radius**2

    def residual(induced_speed):
        thrust, _, _ = axial_loads(rotor, grid, induced_speed)
        return thrust.sum() - momentum_factor * induced_speed * (rotor.axial_speed + induced_speed)

    if residual(0.0) <= 0:
        raise SolverError("当前工况没有正推力解，请提高总距或转速，或降低轴向来流。")
    upper = max(1.0, rotor.omega * rotor.radius * 0.1)
    while residual(upper) > 0 and upper < rotor.omega * rotor.radius:
        upper *= 2
    if residual(upper) > 0:
        raise SolverError("正诱导速度区间内未找到入流平衡。")
    induced, info = brentq(residual, 0.0, upper, xtol=1e-10, full_output=True)
    thrust, tangent, alpha = axial_loads(rotor, grid, induced)
    if alpha.min() < rotor.polar[0, 0] or alpha.max() > rotor.polar[-1, 0]:
        raise SolverError("收敛后的叶素攻角超出翼型表范围，请扩充翼型表或调整工况。")
    torque = tangent * radius
    total_thrust, total_torque = float(thrust.sum()), float(torque.sum())
    if total_torque <= 0:
        raise SolverError("轴扭矩超出正功率推进模型范围。")
    # Positive thrust is +z. For an axial force at [r,0,0], r × F is -y.
    # Opposite azimuths cancel the in-plane moments for symmetric axial flow.
    azimuth = np.arange(rotor.blades) * (2*pi/rotor.blades)
    mx = np.sum(thrust * (np.sin(azimuth)[:, None] * radius))
    my = -np.sum(thrust * (np.cos(azimuth)[:, None] * radius))
    summary = dict(
        thrust_n=total_thrust, torque_nm=total_torque, power_w=rotor.omega * total_torque,
        induced_speed_m_s=induced, iterations=info.iterations, residual_n=float(residual(induced)),
        inflow_mean=induced / (rotor.omega * rotor.radius), inflow_sin=0.0, inflow_cos=0.0,
        moment_x_nm=float(mx), moment_y_nm=float(my),
    )
    headers = ("r_m", "dr_m", "chord_m", "pitch_deg", "alpha_deg",
               "dthrust_n", "dtorque_nm", "thrust_n_per_m", "torque_nm_per_m")
    radial_thrust, radial_torque = thrust.sum(axis=0), torque.sum(axis=0)
    radial = zip(radius, widths, chord, np.rad2deg(pitch), alpha[0], radial_thrust, radial_torque,
                 radial_thrust / widths, radial_torque / widths)
    return summary, headers, radial
