"""A2 mechanics checks; independent mass-point kinematics, tolerance 1e-6.

Force/moment normalization uses m*Omega²*R and m*Omega²*R². Near-zero
matrix entries use 1e-9 SI absolute tolerance, no relaxed physics threshold.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from tools.build_a2_example import synthetic
from rotordesignlab import designs, assembly
from rotordesignlab.mass_partition import Partition, skew, spatial_mass
from rotordesignlab.trim import TrimSystem
from rotordesignlab.coupled_dynamics import CoupledDynamics
from rotordesignlab.cases import run_case, read_case
from rotordesignlab.dynamics import central_derivatives, derivative_check, step_response
from rotordesignlab.airframe import body_to_ned


CASE = dict(schema_version=3, model='helicopter', analysis='trim', speed_m_s=0., climb_m_s=0.,
            altitude_m=0., radial_stations=24, azimuth_stations=24, requested_duration_s=600.)


class CoupledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = TemporaryDirectory()
        cls.root = Path(cls.folder.name)
        cls.design = assembly.from_legacy(synthetic())
        cls.path = designs.materialize(cls.design, cls.root/'input')
        cls.result = run_case(dict(CASE, aircraft_json=str(cls.path)), cls.root, cls.root/'trim')
        assert cls.result['status'] == 'converged', cls.result
        from rotordesignlab.aircraft import read_aircraft
        system = TrimSystem(read_aircraft(cls.root/'trim/aircraft.json'), cls.root/'trim', CASE)
        cls.plant = CoupledDynamics(system, cls.result['diagnostics']['solved_state'], cls.result['velocity_body_m_s'])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_partition_ownership_and_rejections(self):
        partition = Partition(self.design['aircraft'])
        self.assertAlmostEqual(partition.mass, 200-3*2.5-2*.1-1-.05)
        np.testing.assert_allclose(partition.core_matrix, partition.core_matrix.T, atol=1e-10)
        for mutation in ('missing_tail', 'bad_inertia', 'mass_double', 'mismatch', 'eccentric_hub'):
            bad = deepcopy(self.design['aircraft'])
            if mutation == 'missing_tail':
                del bad['rotors'][1]['blade_mass']['mass_kg']
            elif mutation == 'bad_inertia':
                bad['mass_properties']['inertia_cg_kg_m2'] = np.eye(3).tolist()
            elif mutation == 'mass_double':
                bad['mass_properties']['mass_kg'] = 1.
            elif mutation == 'mismatch':
                bad['rotors'][0]['blade_mass']['inertia_kg_m2'] = 1.3
            else:
                bad['rotors'][0]['hub']['cg_rotor_m'][0] = .01
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                Partition(bad)
        roundtrip = designs.unpack(designs.pack(self.design))
        self.assertEqual(roundtrip['aircraft'], self.design['aircraft'])

    def test_mass_matrix_against_independent_point_velocity_maps(self):
        plant = self.plant
        state = plant.state.copy()
        state[15:18] += [.01, .02, -.015]
        _, data = plant.evaluate(state, plant.controls)
        actual = data['mechanics'].matrix
        expected = np.zeros_like(actual)
        partition = plant.system.partition
        expected[:6, :6] = partition.core_matrix
        for role in ('main', 'tail'):
            part = partition.rotors[role]
            model = plant.system.rotors[role]
            if role == 'main':
                spans, weights = np.array([.2, .9]), np.array([15/14, 10/7])
            else:
                nodes, quadrature = np.polynomial.legendre.leggauss(6)
                spans, weights = .135+.105*nodes, .05*quadrature
            h = model.kernel.harmonics
            flap = state[15:18] if role == 'main' else np.zeros(3)
            beta = h@flap
            er = np.column_stack((np.cos(model.kernel.psi), np.sin(model.kernel.psi), np.zeros(len(h))))
            for i, angle in enumerate(beta):
                b = np.cos(angle)*er[i]+[0, 0, np.sin(angle)]
                n = -np.sin(angle)*er[i]+[0, 0, np.cos(angle)]
                for span, dm in zip(spans, weights):
                    point = part['arm']+part['basis']@(model.config['hinge_offset_m']*er[i]+span*b)
                    mapping = np.zeros((3, len(actual)))
                    mapping[:, :6] = np.column_stack((np.eye(3), -skew(point)))
                    if role == 'main':
                        mapping[:, 6:9] = np.outer(part['basis']@(span*n), h[i])
                    expected += dm*model.rotor.blades/len(h)*(mapping.T@mapping)
            expected[:6, :6] += part['transfer'].T@part['hub_matrix']@part['transfer']
        np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-9)
        self.assertGreater(np.linalg.eigvalsh(actual)[0], 0.)
        self.assertGreater(np.linalg.norm(actual[:6, 6:]), .1)

    def test_full_momentum_balance_independent_spatial_time_difference(self):
        plant = self.plant
        state = plant.state.copy()
        state[3:6] = [.08, -.06, .04]
        state[15:18] += [.005, -.004, .003]
        state[18:21] = [.02, -.015, .01]
        derivative, data = plant.evaluate(state, plant.controls)
        acceleration = data['generalized_acceleration']
        rate = state[3:6]
        g = body_to_ned(*state[6:8]).T@np.array([0.,0.,9.80665])
        partition = plant.system.partition
        core_acc = acceleration[:3]+np.cross(acceleration[3:6], partition.cg)+np.cross(rate,np.cross(rate,partition.cg))
        force = partition.mass*(g-core_acc)
        moment = np.cross(partition.cg,force)-partition.inertia@acceleration[3:6]-np.cross(rate,partition.inertia@rate)
        wrench = np.r_[force,moment]
        scale = 1.
        for role in ('main','tail'):
            part, model = partition.rotors[role], plant.system.rotors[role]
            load = data['rotor_data'][role]
            if role == 'main':
                spans, dm = np.array([.2,.9]), np.array([15/14,10/7])
                b0, bd, bdd = state[15:18],state[18:21],acceleration[6:9]
            else:
                nodes, weights = np.polynomial.legendre.leggauss(6)
                spans, dm = .135+.105*nodes,.05*weights
                b0,bd,bdd = np.zeros(3),np.zeros(3),np.zeros(3)
            def positions(time):
                psi = model.kernel.psi+model.kernel.rotation_sign*model.rotor.omega*time
                h = np.column_stack((np.ones(len(psi)),np.cos(psi),np.sin(psi)))
                beta = h@(b0+bd*time+.5*bdd*time*time)
                er = np.column_stack((np.cos(psi),np.sin(psi),np.zeros(len(psi))))
                x = (model.config['hinge_offset_m']+np.cos(beta)[:,None]*spans)[:,:,None]*er[:,None,:]
                x[:,:,2] = np.sin(beta)[:,None]*spans
                body = x@part['basis'].T+part['arm']
                return body@Rotation.from_rotvec(rate*time+.5*acceleration[3:6]*time*time).as_matrix().T+.5*acceleration[:3]*time*time
            dt = 2e-6
            pos = positions(0.)
            acc = (-positions(2*dt)+16*positions(dt)-30*pos+16*positions(-dt)-positions(-2*dt))/(12*dt*dt)
            force = model.rotor.blades*np.mean(np.einsum('nsi,s->ni',g-acc,dm),axis=0)
            moment = model.rotor.blades*np.mean(np.einsum('nsi,s->ni',np.cross(pos,g-acc),dm),axis=0)
            aero = part['transfer'].T@np.r_[load['force'],load['moment']]
            wrench += aero+np.r_[force,moment]
            hub = part['hub']
            hub_point = part['arm']+part['basis']@hub['cg_rotor_m']
            j = part['basis']@np.asarray(hub['inertia_cg_kg_m2'])@part['basis'].T
            force = hub['mass_kg']*(g-acceleration[:3]-np.cross(acceleration[3:6],hub_point)-np.cross(rate,np.cross(rate,hub_point)))
            spin = part['basis'][:,2]*hub['inertia_cg_kg_m2'][2][2]*model.kernel.rotation_sign*model.rotor.omega
            wrench += np.r_[force,np.cross(hub_point,force)-j@acceleration[3:6]-np.cross(rate,j@rate+spin)]
            scale += model.rotor.blades*part['blade'].mass_kg*model.rotor.omega**2*max(model.rotor.radius,model.rotor.radius**2)
        for name,item in data['components'].items():
            if name not in ('main','tail'):
                wrench += np.r_[item['force_body_n'],item.get('moment_cg_body_nm',[0,0,0])]
        self.assertLess(np.max(abs(wrench))/scale,1e-6)
        self.assertLess(data['implicit_balance_error'],1e-9)

    def test_trim_equilibrium_and_actual_mass_matrix_derivatives(self):
        plant = self.plant
        self.assertEqual(len(plant.state),21)
        self.assertLess(np.max(abs(plant.rhs(plant.state,plant.controls))),1e-6)
        a,b = central_derivatives(plant)
        fine_a,fine_b = central_derivatives(plant,.5)
        self.assertTrue(derivative_check(a,b,fine_a,fine_b,plant.state_scale)['passed'])
        # Independent implicit residual: E (nonlinear derivative - perturbation)
        # has exactly the generalized force balance and kinematic units.
        offset=np.linspace(-1.,1.,21)*1e-6
        nonlinear=plant.rhs(plant.state+offset,plant.controls)
        np.testing.assert_allclose(plant.mass_matrix@nonlinear,plant.mass_matrix@fine_a@offset,rtol=.02,atol=1e-5)

    def test_zero_slow_rates_preserve_periodic_kernel(self):
        model=self.plant.system.rotors['main']
        x=self.plant.trim[6:12]
        control=self.plant.controls[:3]
        args=(x,control,[0,0,0])
        old=model.evaluate(*args)
        explicit=model.evaluate(*args,flap_rates=np.zeros(3),flap_accelerations=np.zeros(3))
        np.testing.assert_array_equal(old[0],explicit[0])
        np.testing.assert_array_equal(old[1]['force'],explicit[1]['force'])

    def test_both_hinged_rotors_and_opposite_rotation(self):
        for sign in (-1, 1):
            aircraft=deepcopy(self.plant.system.aircraft)
            tail=aircraft['rotors'][1]
            tail['rotation_sign']=sign
            tail['flight']['flapping'].update(mode='hinged',spring_nm_rad=0.,damper_nms_rad=0.)
            system=TrimSystem(aircraft,self.root/'trim',CASE)
            plant=CoupledDynamics(system,self.plant.trim,self.plant.state[:3])
            self.assertEqual(len(plant.state),27)
            derivative,data=plant.evaluate(plant.state,plant.controls)
            matrix=data['mechanics'].matrix
            np.testing.assert_allclose(matrix,matrix.T,atol=1e-10)
            self.assertGreater(np.linalg.eigvalsh(matrix)[0],0.)
            self.assertGreater(np.linalg.norm(matrix[:6,9:12]),.001)
            self.assertLess(data['implicit_balance_error'],1e-9)
            self.assertTrue(np.isfinite(derivative).all())


if __name__ == '__main__':
    unittest.main()
