"""First-harmonic dynamic blade amplitudes and implicit body acceleration.

No frozen-amplitude derivative approximation: b, db/dt are states and d²b/dt²
is solved with body acceleration from the symmetric generalized inertia.
Revolution averaging excludes blade-passage loads, lead-lag and elastic DOFs.
"""
import numpy as np
from scipy.linalg import block_diag
from .dynamics import STATES, UNITS, STATE_STEPS, STATE_SCALE, APPARENT_MASS
from .airframe import body_to_ned
from .steady_rotor import pitt_peters


class CoupledDynamics:
    def __init__(self, system, trim_state, trim_velocity):
        self.system = system
        self.trim = np.asarray(trim_state)
        self.controls = self.trim[:4].copy()
        self.roles = [r for r in ('main', 'tail') if not system.rotors[r].fixed]
        self.state_names = list(STATES)
        self.state_units = list(UNITS)
        self.state = np.r_[trim_velocity, np.zeros(3), self.trim[4:6], 0., self.trim[6:9], self.trim[12:15]]
        self.indices = {}
        for role in self.roles:
            start = len(self.state)
            self.indices[role] = start
            self.state_names += [role+'_beta'+s for s in ('0', 'c', 's')]
            self.state_names += [role+'_beta'+s+'_rate' for s in ('0', 'c', 's')]
            self.state_units += ['rad']*3+['rad/s']*3
            trim_index = 9 if role == 'main' else 15
            self.state = np.r_[self.state, self.trim[trim_index:trim_index+3], np.zeros(3)]
        self.state_steps = np.r_[STATE_STEPS*.1, np.full(6*len(self.roles), 1e-6)]
        self.control_steps = np.full(4, 1e-5)
        self.state_scale = np.r_[STATE_SCALE, np.full(6*len(self.roles), .05)]
        _, data = self.evaluate(self.state, self.controls)
        matrix = data['mechanics'].matrix
        indices = list(range(6))
        for role in self.roles:
            indices.extend(range(self.indices[role]+3, self.indices[role]+6))
        self.mass_matrix = np.eye(len(self.state))
        self.mass_matrix[np.ix_(indices, indices)] = matrix
        for role, index in [('main', 9), ('tail', 12)]:
            self.mass_matrix[index:index+3, index:index+3] = np.diag(APPARENT_MASS/system.rotors[role].rotor.omega)
        self.mass_matrix_definition = ('E is the actual implicit acceleration Jacobian at trim: '
            'body/blade generalized mass incl. off-diagonal coupling, kinematics identity, PP M/Omega. '
            'States u/v/w refer to the fixed reference CG; F=E*A, G=E*B. '
            'Blade harmonic amplitudes and their time derivatives are explicit states.')

    def evaluate(self, state, controls, strict=True):
        state, controls = np.asarray(state), np.asarray(controls)
        if state.shape != self.state.shape or controls.shape != (4,) or not np.isfinite(np.r_[state, controls]).all():
            raise ValueError('动态状态或操纵维度/有限值无效。')
        velocity, rates, angles = state[:3], state[3:6], state[6:9]
        low, high = self.system.bounds()
        if strict and (np.any(controls < low[:4]) or np.any(controls > high[:4]) or
                       np.any(angles[:2] < low[4:6]) or np.any(angles[:2] > high[4:6])):
            raise ValueError('动态姿态或操纵超出限制。')
        x = self.trim.copy()
        x[:4], x[4:6] = controls, angles[:2]
        x[6:9], x[12:15] = state[9:12], state[12:15]
        flap_rates = {}
        for role, rotor_index in [('main', 6), ('tail', 12)]:
            model = self.system.rotors[role]
            inflow = x[rotor_index:rotor_index+3]
            rotor_low, rotor_high = model.bounds()
            if strict and (np.any(inflow < rotor_low[:3]) or np.any(inflow > rotor_high[:3])):
                raise ValueError(role+'：入流状态超出支持范围。')
            if role in self.indices:
                start = self.indices[role]
                x[rotor_index+3:rotor_index+6] = state[start:start+3]
                flap_rates[role] = state[start+3:start+6]
        _, data = self.system.loads(x, velocity, rates, strict, require_equilibrium=False,
                                    flap_rates=flap_rates, dynamic_flap=True)
        mechanics = data['mechanics']
        # Congruence-scaled positivity guards impossible partitions or singular DOFs.
        diagonal = np.sqrt(np.diag(mechanics.matrix))
        normalized = mechanics.matrix/np.outer(diagonal, diagonal)
        if not np.isfinite(normalized).all() or np.linalg.eigvalsh(normalized)[0] <= 1e-9:
            raise ValueError('耦合质量矩阵不是可解的正定系统。')
        acceleration = np.linalg.solve(mechanics.matrix, mechanics.rhs)
        error = mechanics.matrix@acceleration-mechanics.rhs
        data['implicit_balance_error'] = float(np.max(abs(error)/np.maximum(abs(mechanics.rhs), 1.)))
        phi, theta = angles[:2]
        if abs(np.cos(theta)) < .2:
            raise ValueError('Euler姿态接近奇异。')
        kinematics = np.array([[1, np.sin(phi)*np.tan(theta), np.cos(phi)*np.tan(theta)],
                               [0, np.cos(phi), -np.sin(phi)],
                               [0, np.sin(phi)/np.cos(theta), np.cos(phi)/np.cos(theta)]])
        derivative = np.zeros_like(state)
        derivative[:3] = acceleration[:3]-np.cross(rates, velocity)
        derivative[3:6] = acceleration[3:6]
        derivative[6:9] = kinematics@rates
        cg = np.asarray(self.system.aircraft['mass_properties']['cg_m'])
        for role, start, inflow_index in [('main', 6, 9), ('tail', 12, 12)]:
            model, basis = self.system.rotors[role], self.system.bases[role]
            arm = np.asarray(self.system.selected[role]['position_m'])-cg
            velocity_hub = basis.T@(velocity+np.cross(rates, arm))
            loads = data['rotor_data'][role]
            derivative[inflow_index:inflow_index+3] = pitt_peters(state[inflow_index:inflow_index+3],
                velocity_hub/(model.rotor.omega*model.rotor.radius), loads['force'][2]/model.scale,
                loads['pressure_moments']/(model.scale*model.rotor.radius), dynamic=True, omega=model.rotor.omega)[0]
        for role in self.roles:
            start = self.indices[role]
            derivative[start:start+3] = state[start+3:start+6]
            derivative[start+3:start+6] = acceleration[mechanics.slices[role]]
        data['generalized_acceleration'] = acceleration
        return derivative, data

    def rhs(self, state, controls):
        return self.evaluate(state, controls)[0]
