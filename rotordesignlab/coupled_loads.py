"""Joint, revolution-averaged blade/core Newton--Euler equations (SI).

Generalized accelerations are [inertial a_O, body alpha, harmonic b_ddot].
Harmonic b_dot is a state, not silently frozen. Full H b_ddot+2 H_dot b_dot
and centripetal terms are retained. No aerodynamic model is replaced here.
"""
import numpy as np
from .hub_loads import blade_motion, blade_on_hub
from .mass_partition import skew


class Mechanics:
    def __init__(self, system, rates, gravity):
        self.partition = system.partition
        self.roles = [role for role in ('main', 'tail') if not system.rotors[role].fixed]
        self.slices = {role: slice(6+3*i, 9+3*i) for i, role in enumerate(self.roles)}
        size = 6+3*len(self.roles)
        self.matrix = np.zeros((size, size))
        self.matrix[:6, :6] = self.partition.core_matrix
        self.rhs = np.zeros(size)
        self.rhs[:6] = self.partition.core_bias(np.asarray(rates), np.asarray(gravity))
        self.rates = np.asarray(rates)
        self.gravity = np.asarray(gravity)

    def rotor(self, role, model, loads, residual):
        part = self.partition.rotors[role]
        mass, basis, arm = part['blade'], part['basis'], part['arm']
        rotation = basis.T@self.rates
        gravity = basis.T@self.gravity
        # a_h = a_O + alpha x arm + omega x (omega x arm).
        # Unknown a_O/alpha are assembled below; the centrifugal bias stays here.
        hub_bias = basis.T@np.cross(self.rates, np.cross(self.rates, arm))
        motion = blade_motion(model.kernel.psi, loads['beta'], loads['beta_dot'], loads['beta_ddot'],
                              model.rotor.omega, model.kernel.rotation_sign, model.config['hinge_offset_m'],
                              body_rates=rotation, hub_acceleration=hub_bias)
        force = loads['element_force'].sum(axis=1)
        moment = np.cross(loads['position'], loads['element_force']).sum(axis=1)
        transmitted = blade_on_hub(motion, mass, force, moment, gravity=gravity)
        count = model.rotor.blades
        transfer = part['transfer']
        local = np.r_[count*transmitted['force'].mean(axis=0), count*transmitted['moment'].mean(axis=0)]
        matrix = count*transmitted['mass_matrix'].mean(axis=0)+part['hub_matrix']
        hub = part['hub']
        hub_cg = np.asarray(hub['cg_rotor_m'])
        hub_j = np.asarray(hub['inertia_cg_kg_m2'])
        hub_force = hub['mass_kg']*(gravity-hub_bias-np.cross(rotation, np.cross(rotation, hub_cg)))
        spin_momentum = np.array([0., 0., hub_j[2, 2]*model.kernel.rotation_sign*model.rotor.omega])
        hub_moment = np.cross(hub_cg, hub_force)-np.cross(rotation, hub_j@rotation+spin_momentum)
        local += np.r_[hub_force, hub_moment]
        wrench = transfer.T@local
        self.matrix[:6, :6] += transfer.T@matrix@transfer
        self.rhs[:6] += wrench
        if role in self.slices:
            index = self.slices[role]
            h = model.kernel.harmonics
            normal = motion['normal']
            # Virtual displacement for each amplitude is s*n*H_j.
            f = mass.first_moment_kg_m*normal
            m = (mass.first_moment_kg_m*np.cross(motion['origin'], normal)
                 + mass.second_moment_kg_m2*np.cross(motion['span'], normal))
            cross = count*np.einsum('ni,nj->ij', np.column_stack((f, m)), h)/len(h)
            cross = transfer.T@cross
            self.matrix[:6, index] = cross
            self.matrix[index, :6] = cross.T
            self.matrix[index, index] = count*mass.second_moment_kg_m2*(h.T@h)/len(h)
            # SteadyRotor returns [mean,2*cos,2*sin] of its dimensionless defect.
            # Unscale to virtual-work forces, keeping the same mass and gravity.
            self.rhs[index] = -residual[3:]*count*mass.second_moment_kg_m2*model.rotor.omega**2/np.array([1., 2., 2.])
        return wrench, dict(blades_force_hub_rotor_n=(count*transmitted['force'].mean(axis=0)).tolist(),
                            blades_moment_hub_rotor_nm=(count*transmitted['moment'].mean(axis=0)).tolist(),
                            hub_force_rotor_n=hub_force.tolist(), hub_moment_rotor_nm=hub_moment.tolist())
