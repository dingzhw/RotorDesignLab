"""Rotor/core mass ownership about the fixed reference CG, in body SI axes.

The supplied total inertia is revolution-averaged at explicitly stated flap
harmonics. Subtraction is permitted only with that declaration and complete
blade/hub mass data. No lower-bound mass is inferred from m1²/I.
"""
from copy import deepcopy
import numpy as np
from .azimuth import rotor_basis
from .hub_loads import BladeMass, blade_motion, blade_on_hub

MODEL = 'harmonic_hub_v1'
LEGACY = 'legacy_aero_v1'


def enabled(aircraft):
    return aircraft.get('dynamics', {}).get('model', LEGACY) == MODEL


def skew(value):
    x, y, z = value
    return np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])


def spatial_mass(mass, position, inertia):
    arm = skew(position)
    return np.block([[mass*np.eye(3), -mass*arm],
                     [mass*arm, np.asarray(inertia)-mass*arm@arm]])


def transform(basis, arm):
    """Local hub twist = T * reference-point body twist; wrench uses T.T."""
    return np.block([[basis.T, -basis.T@skew(arm)], [np.zeros((3, 3)), basis.T]])


def properties(matrix):
    mass = float(np.trace(matrix[:3, :3])/3)
    if mass <= 0:
        raise ValueError('扣除旋转部件后机体质量必须大于零。')
    c = matrix[3:, :3]
    position = np.array([c[2, 1], c[0, 2], c[1, 0]])/mass
    inertia = matrix[3:, 3:] + mass*skew(position)@skew(position)
    eig = np.linalg.eigvalsh(inertia)
    if not np.allclose(inertia, inertia.T, atol=1e-9) or eig[0] <= 0 or eig[-1] > eig[:2].sum()+1e-8:
        raise ValueError('扣除旋转部件后的非旋转机体惯量不满足正定性/三角关系，请核对总惯量归属。')
    return mass, position, inertia


class Partition:
    def __init__(self, aircraft):
        cfg = aircraft['dynamics']
        if cfg['model'] != MODEL or cfg['mass_reference'] != 'total_at_reference_flap':
            raise ValueError('新模型要求明确的全机参考挥舞构型质量归属。')
        props = aircraft['mass_properties']
        self.origin = np.asarray(props['cg_m'], dtype=float)
        total = spatial_mass(props['mass_kg'], np.zeros(3), props['inertia_cg_kg_m2'])
        self.core_matrix = total.copy()
        self.rotors = {}
        rows = []
        if set(cfg['reference_flap_deg']) != {r['id'] for r in aircraft['rotors']}:
            raise ValueError('参考挥舞构型须逐一对应安装编号。')
        psi = np.arange(360)*2*np.pi/360
        harmonics = np.column_stack((np.ones_like(psi), np.cos(psi), np.sin(psi)))
        for rotor in aircraft['rotors']:
            label = rotor['id']
            required = ('mass_kg', 'first_mass_moment_kg_m', 'inertia_kg_m2', 'provenance')
            mass = rotor.get('blade_mass', {})
            hub = rotor.get('hub', {})
            missing = [label+'/blade_mass/'+k for k in required if k not in mass]
            missing += [label+'/hub/'+k for k in ('mass_kg', 'cg_rotor_m', 'inertia_cg_kg_m2', 'provenance') if k not in hub]
            if missing:
                raise ValueError('质量分账缺少：'+', '.join(missing))
            flap = rotor['flight']['flapping']
            blade = BladeMass(mass['mass_kg'], mass['first_mass_moment_kg_m'], mass['inertia_kg_m2'],
                              rotor['radius_m']-flap['hinge_offset_m'])
            for key in ('first_mass_moment_kg_m', 'inertia_kg_m2'):
                if key in flap and not np.isclose(flap[key], mass[key], rtol=1e-12, atol=1e-12):
                    raise ValueError(label+'：挥舞质量矩与模块质量分账不一致。')
            hub_cg = np.asarray(hub['cg_rotor_m'], dtype=float)
            hub_j = np.asarray(hub['inertia_cg_kg_m2'], dtype=float)
            # An axisymmetric, shaft-centred rotating hub admits a fixed averaged
            # tensor and spin momentum Jzz*sigma*Omega. Eccentric hubs need phase DOF.
            if not np.allclose(hub_cg[:2], 0, atol=1e-12) or not np.allclose(hub_j, np.diag(np.diag(hub_j)), atol=1e-12) or not np.isclose(hub_j[0, 0], hub_j[1, 1], rtol=1e-10):
                raise ValueError(label+'：当前仅支持轴上重心、轴对称旋转桨毂惯量。')
            hub_k = spatial_mass(hub['mass_kg'], hub_cg, hub_j)
            properties(hub_k)
            basis = rotor_basis(rotor['thrust_axis_body'], rotor['flight']['x_reference_body'])
            arm = np.asarray(rotor['position_m'])-self.origin
            transfer = transform(basis, arm)
            beta = harmonics @ np.deg2rad(cfg['reference_flap_deg'][label])
            if np.max(abs(beta)) > np.deg2rad(flap['max_flap_deg']) + 1e-12:
                raise ValueError(label+'：参考挥舞构型超出限位。')
            motion = blade_motion(psi, beta, np.zeros(360), np.zeros(360), 1., rotor['rotation_sign'], flap['hinge_offset_m'])
            zero = np.zeros((360, 3))
            blade_k = rotor['blade_count']*blade_on_hub(motion, blade, zero, zero)['mass_matrix'].mean(axis=0)
            local = blade_k+hub_k
            self.core_matrix -= transfer.T@local@transfer
            self.rotors[rotor['role']] = dict(blade=blade, hub=deepcopy(hub), basis=basis, arm=arm,
                                            transfer=transfer, hub_matrix=hub_k)
            rows.append(dict(rotor_id=label, blade_count=rotor['blade_count'], per_blade_mass_kg=blade.mass_kg,
                             blades_mass_kg=rotor['blade_count']*blade.mass_kg, hub_mass_kg=hub['mass_kg'],
                             reference_flap_deg=cfg['reference_flap_deg'][label],
                             blade_source=mass['provenance'], hub_source=hub['provenance']))
        self.mass, self.cg, self.inertia = properties(self.core_matrix)
        self.report = dict(model=MODEL, reference_origin_m=self.origin.tolist(),
                           total_reference_mass_kg=props['mass_kg'], components=rows,
                           core_mass_kg=self.mass, core_cg_m=(self.cg+self.origin).tolist(),
                           core_inertia_cg_kg_m2=self.inertia.tolist(),
                           reference_flap_deg=cfg['reference_flap_deg'], provenance=cfg['provenance'],
                           note='总惯量为明确参考挥舞构型下的方位平均值；机体不含主尾桨桨叶及旋转桨毂。状态速度参考该固定原点，实际系统重心随挥舞变化。')

    def core_bias(self, rates, gravity):
        """Gravity minus centripetal/gyroscopic inertia, about fixed reference O."""
        centrifugal = np.cross(rates, np.cross(rates, self.cg))
        force = self.mass*(gravity-centrifugal)
        moment = np.cross(self.cg, force)-np.cross(rates, self.inertia@rates)
        return np.r_[force, moment]
