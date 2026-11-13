"""Rigid coned blade elements with uniform or annular axial momentum inflow.

No swirl, root loss, fitted induced-power factor or elastic blade motion.
Annular mode uses conventional Prandtl tip loss in the momentum equation.
"""
from math import pi

import numpy as np
from scipy.optimize import brentq

from .rotor import SolverError


def prandtl_tip(blades, r_over_R, phi):
    exponent = blades/2*(1-r_over_R)/(r_over_R*np.maximum(np.abs(np.sin(phi)), 1e-12))
    return 2/pi*np.arccos(np.exp(-np.maximum(exponent, 0)))


def solve_axial(rotor):
    radius, widths, chord, pitch = rotor.grid()
    cone = np.cos(np.deg2rad(rotor.precone_deg))
    arm = radius*cone
    tangent = rotor.omega*arm
    span = radius/rotor.radius

    def elements(induced, strict=False):
        axial = (rotor.axial_speed+induced)*cone
        phi = np.arctan2(axial, tangent)
        alpha = np.rad2deg(pitch-phi)
        speed = np.hypot(tangent, axial)
        mach = speed/rotor.speed_of_sound
        if rotor.airfoil_grid is not None:
            cl, cd = rotor.airfoil_grid.coefficients(span, alpha, mach,
                reynolds=rotor.density*speed*chord/rotor.dynamic_viscosity, strict=strict)
        else:
            if strict and (alpha.min() < rotor.polar[0,0] or alpha.max() > rotor.polar[-1,0]):
                raise SolverError('Converged element angle exceeds the polar domain.')
            cl = np.interp(alpha, rotor.polar[:,0], rotor.polar[:,1])
            cd = np.interp(alpha, rotor.polar[:,0], rotor.polar[:,2])
        force_scale = .5*rotor.density*speed**2*chord*widths*rotor.blades
        normal = force_scale*(cl*np.cos(phi)-cd*np.sin(phi))
        thrust = normal*cone
        torque = force_scale*(cl*np.sin(phi)+cd*np.cos(phi))*arm
        loss = prandtl_tip(rotor.blades, span, phi) if rotor.tip_loss == 'prandtl' else np.ones_like(span)
        return thrust, torque, alpha, mach, cl, cd, loss

    disk_area = pi*(rotor.radius*cone)**2
    if rotor.inflow_model == 'uniform':
        def residual(value):
            return elements(value)[0].sum()-2*rotor.density*disk_area*value*(rotor.axial_speed+value)
        if residual(0) <= 0:
            raise SolverError('No positive-thrust uniform inflow solution.')
        high = rotor.omega*rotor.radius
        if residual(high) >= 0:
            raise SolverError('Uniform inflow root is not bracketed.')
        value, info = brentq(residual, 0, high, xtol=1e-10, full_output=True)
        induced = np.full(rotor.stations, value)
        residual_total = float(residual(value))
        residual_max = abs(residual_total)
        iterations = info.iterations
    else:
        factor = 4*pi*rotor.density*arm*(widths*cone)
        def residual(value):
            thrust, *_, loss = elements(value)
            return thrust-factor*loss*value*(rotor.axial_speed+value)
        low = np.zeros(rotor.stations)
        high = np.full(rotor.stations, rotor.omega*rotor.radius)
        if np.any(residual(low) <= 0) or np.any(residual(high) >= 0):
            raise SolverError('Annular positive-induction branch is not bracketed at every element.')
        for iterations in range(1, 61):
            middle = (low+high)/2
            positive = residual(middle) > 0
            low = np.where(positive, middle, low)
            high = np.where(positive, high, middle)
            if np.max(high-low) < 1e-9:
                break
        induced = (low+high)/2
        closure = residual(induced)
        residual_total = float(closure.sum())
        residual_max = float(np.max(np.abs(closure)))
    thrust, torque, alpha, mach, cl, cd, loss = elements(induced, strict=True)
    total_thrust, total_torque = float(thrust.sum()), float(torque.sum())
    if total_torque <= 0 or residual_max > max(1e-5, total_thrust*1e-8):
        raise SolverError('Invalid drive torque or unconverged axial momentum balance.')
    tip = rotor.omega*rotor.radius
    # Coefficients use nominal R, as in the source experiments, not projected R.
    scale = rotor.density*pi*rotor.radius**2*tip**2
    mean = float(np.average(induced, weights=arm*widths))
    summary = dict(thrust_n=total_thrust, torque_nm=total_torque, power_w=rotor.omega*total_torque,
        induced_speed_m_s=mean, induced_min_m_s=float(induced.min()), induced_max_m_s=float(induced.max()),
        iterations=iterations, residual_n=residual_total, max_element_residual_n=residual_max,
        inflow_mean=mean/tip, inflow_sin=0., inflow_cos=0., moment_x_nm=0., moment_y_nm=0.,
        rpm=rotor.omega*30/pi, collective_deg=rotor.collective_deg, thrust_coefficient=total_thrust/scale,
        torque_coefficient=total_torque/(scale*rotor.radius), power_coefficient=total_torque/(scale*rotor.radius),
        tip_speed_m_s=tip, alpha_min_deg=float(alpha.min()), alpha_max_deg=float(alpha.max()),
        mach_min=float(mach.min()), mach_max=float(mach.max()),
        propulsive_efficiency=total_thrust*rotor.axial_speed/(rotor.omega*total_torque))
    if rotor.axial_speed == 0:
        summary['hover_figure_of_merit'] = total_thrust**1.5/(np.sqrt(2*rotor.density*pi*rotor.radius**2)*rotor.omega*total_torque)
    columns = ('r_m','dr_m','chord_m','pitch_deg','alpha_deg','dthrust_n','dtorque_nm',
               'thrust_n_per_m','torque_nm_per_m','induced_speed_m_s','mach','cl','cd','tip_loss_factor',
               'section_thrust_coefficient')
    # Section thrust normalized with local rotational speed, suitable for a pressure-integral comparison.
    sectional = thrust/(.5*rotor.density*tangent**2*chord*widths*rotor.blades)
    return summary, columns, zip(radius,widths,chord,np.rad2deg(pitch),alpha,thrust,torque,
        thrust/widths,torque/widths,induced,mach,cl,cd,loss,sectional)
