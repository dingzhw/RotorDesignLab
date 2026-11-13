"""Target-thrust solves using the same blade elements and axial momentum balance."""

from dataclasses import replace
from math import pi, sqrt

import numpy as np
from scipy.optimize import brentq

from .rotor import SolverError, axial_loads, solve


def solve_target(rotor, target, limits):
    if not isinstance(target, dict) or set(target) - {'thrust_n', 'solve_for', 'bounds'}:
        raise ValueError('target 只接受 thrust_n、solve_for 和 bounds。')
    thrust = target.get('thrust_n')
    variable = target.get('solve_for')
    if type(thrust) not in (int, float) or not np.isfinite(thrust) or thrust <= 0:
        raise ValueError('目标拉力必须为有限正数。')
    if variable not in ('rpm', 'collective_deg'):
        raise ValueError('solve_for 必须为 collective_deg 或 rpm。')
    bounds = target.get('bounds', limits[variable])
    if (not isinstance(bounds, list) or len(bounds) != 2 or
        any(type(value) not in (int, float) or not np.isfinite(value) for value in bounds)):
        raise ValueError('反求 bounds 必须为两个有限数值。')
    low, high = bounds
    if not limits[variable][0] <= low < high <= limits[variable][1]:
        raise ValueError('反求区间必须在机型限制内，且下限小于上限。')
    if variable == 'rpm' and np.hypot(high * pi / 30 * rotor.radius, rotor.axial_speed) > 250:
        raise ValueError('反求转速上限使叶尖合速度超过当前模型的 250 m/s 上限。')
    # From T = 2 rho A vi (V + vi), avoiding cancellation for small T / large V.
    rho_area = rotor.density * pi * rotor.radius**2
    induced = thrust / (rho_area * (sqrt(rotor.axial_speed**2 + 2 * thrust / rho_area) + rotor.axial_speed))

    def changed(value):
        return replace(rotor, **({'omega': value * pi / 30} if variable == 'rpm' else {variable: value}))

    def residual(value):
        model = changed(value)
        loads, _, _ = axial_loads(model, model.grid(), induced)
        return float(loads.sum()) - thrust

    # Detect multiple sign-changing roots rather than silently choosing a stalled branch.
    samples = np.linspace(low, high, 129)
    values = [residual(value) for value in samples]
    roots = [float(x) for x, value in zip(samples, values) if abs(value) <= max(1e-8, thrust * 1e-10)]
    for left, right, fleft, fright in zip(samples[:-1], samples[1:], values[:-1], values[1:]):
        if fleft * fright < 0:
            roots.append(float(brentq(residual, left, right, xtol=1e-10)))
    candidates = []
    reasons = []
    for root in sorted(roots):
        if candidates and abs(root - candidates[-1][0]) < 1e-7:
            continue
        model = changed(root)
        try:
            answer = solve(model)
            relative = abs(answer[0]['thrust_n'] / thrust - 1)
            if relative > 1e-6:
                raise SolverError('反求后的正算拉力未达到内部一致性容差。')
            candidates.append((root, model, answer, relative))
        except SolverError as error:
            reasons.append(str(error))
    if not candidates:
        detail = (' ' + '; '.join(sorted(set(reasons)))) if reasons else ''
        raise SolverError(f'在给定区间 [{low}, {high}] 内未找到有效的目标拉力解。{detail}')
    if len(candidates) != 1:
        raise SolverError('反求区间存在多个有效解，请收窄 bounds。')
    value, solved, answer, error = candidates[0]
    diagnostic = dict(solve_for=variable, value=value, target_thrust_n=thrust,
                      relative_thrust_error=error, bounds=[low, high], search_samples=len(samples))
    return solved, answer, diagnostic
