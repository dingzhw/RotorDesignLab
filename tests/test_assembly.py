from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import numpy as np

from rotordesignlab import assembly, designs, rotor_module, module_workspace, analysis_history
from rotordesignlab.cases import run_case, read_case
from rotordesignlab.coordinates import selected_basis, attitude_matrix
from rotordesignlab.hover import apply_design


class AssemblyTests(unittest.TestCase):
    def test_legacy_conversion_roundtrip_and_tamper_detection(self):
        for name in list(designs.TEMPLATES)[:2]:
            old = designs.from_template(name)
            before = deepcopy(old)
            new = assembly.from_legacy(old)
            self.assertEqual(old, before)
            self.assertEqual(new['aircraft'], old['aircraft'])
            self.assertEqual(new['assets'], old['assets'])
            saved = designs.unpack(designs.pack(new))
            self.assertEqual(saved['assembly'], new['assembly'])
            bad = deepcopy(new)
            bad['assembly']['instances'][0]['snapshot']['module']['rotor']['radius_m'] *= 1.1
            self.assertIn('哈希', designs.issues(bad)[0])
            bad = deepcopy(new)
            bad['aircraft']['rotors'][0]['radius_m'] *= 1.1
            self.assertIn('不一致', designs.issues(bad)[0])
            bad = deepcopy(new)
            bad['assembly']['instances'][0]['installation']['flight']['flapping'] = {}
            self.assertTrue(designs.issues(bad))
            for field, value in [('rpm', 0.), ('rpm', float('nan'))]:
                bad = deepcopy(new)
                bad['assembly']['instances'][0]['installation']['defaults'][field] = value
                self.assertTrue(designs.issues(bad))
            bad = deepcopy(new)
            bad['assembly']['instances'][0]['installation']['transmission_efficiency'] = 0.
            self.assertTrue(designs.issues(bad))
        old = designs.from_template(list(designs.TEMPLATES)[2])
        with self.assertRaisesRegex(ValueError, '完整'):
            assembly.from_legacy(old)

    def test_independent_instances_and_library_updates(self):
        design = assembly.from_legacy(designs.from_template(next(iter(designs.TEMPLATES))))
        draft = module_workspace.template(next(iter(module_workspace.TEMPLATES)))
        with TemporaryDirectory() as directory:
            identifier, version = module_workspace.save(draft, library=directory)
            loaded, _ = module_workspace.load(identifier, directory)
            source = dict(kind='module_library', identifier=identifier, revision_sha256=version)
            first = assembly.install(design, 0, loaded['module'], loaded['assets'], source)
            both = assembly.install(first, 1, loaded['module'], loaded['assets'], source)
            self.assertEqual(both['assembly']['instances'][0]['snapshot'], both['assembly']['instances'][1]['snapshot'])
            both['assembly']['instances'][1]['installation']['position_m'][0] -= .4
            self.assertEqual(both['assembly']['instances'][0]['installation']['position_m'], design['aircraft']['rotors'][0]['position_m'])
            self.assertEqual(both['aircraft']['mass_properties'], design['aircraft']['mass_properties'])
            old_snapshot = deepcopy(first['assembly'])
            loaded['module']['rotor']['radius_m'] = 1.2
            module_workspace.save(loaded, identifier, version, directory)
            self.assertEqual(first['assembly'], old_snapshot)
            self.assertEqual(first['aircraft']['rotors'][0]['radius_m'], 1.1)
            updated = assembly.install(first, 0, loaded['module'], loaded['assets'], source)
            self.assertEqual(updated['aircraft']['rotors'][0]['radius_m'], 1.2)
            self.assertEqual(updated['assembly']['instances'][0]['installation'], first['assembly']['instances'][0]['installation'])

    def test_rotor_basis_gravity_sign_and_cg_shift(self):
        design = assembly.from_legacy(designs.from_template(next(iter(designs.TEMPLATES))))
        local_flow = np.array([8., 2., -1.])
        for index in (0, 1):
            for sign in (-1, 1):
                with self.subTest(index=index, sign=sign), TemporaryDirectory() as directory:
                    root = Path(directory)
                    module, assets = assembly.module_data(design['assembly']['instances'][index])
                    module['rotor']['rotation_sign'] = sign
                    case_design = assembly.install(design, index, module, assets, {'kind': 'test'})
                    rotor = case_design['aircraft']['rotors'][index]
                    basis = selected_basis(rotor)
                    self.assertAlmostEqual(np.linalg.det(basis), 1.)
                    path = designs.materialize(case_design, root/'aircraft')
                    rotor_module.save(module, assets, root/'module.rdlr')
                    common = dict(rpm=rotor['defaults']['rpm'], collective_deg=rotor['defaults']['collective_deg'],
                                  radial_stations=24, azimuth_stations=24, cyclic_cos_deg=.1, cyclic_sin_deg=-.1,
                                  environment={'mode': 'isa', 'isa_temperature_offset_k': 0.})
                    body = dict(schema_version=2, model='spatial_rotor', aircraft_json=str(path),
                                rotor_id=rotor['id'], flow_body_m_s=(basis@local_flow).tolist(), attitude_deg=[7., -4.],
                                flapping_model='aircraft', **common)
                    local = dict(schema_version=4, model='rotor_module', module_file='module.rdlr', method='spatial',
                                 flapping_model='module', flow_rotor_m_s=local_flow.tolist(),
                                 gravity_rotor_m_s2=(basis.T@attitude_matrix([7., -4.]).T@np.array([0., 0., 9.80665])).tolist(), **common)
                    a = run_case(body, root, root/'installed')
                    b = run_case(local, root, root/'isolated')
                    self.assertEqual(a['status'], 'converged', a)
                    self.assertEqual(b['status'], 'converged', b)
                    force = basis@b['force_rotor_n']
                    moment = basis@b['moment_hub_rotor_nm']
                    arm = np.array(rotor['position_m'])-case_design['aircraft']['mass_properties']['cg_m']
                    np.testing.assert_allclose(a['installation']['force_body_n'], force, rtol=1e-6, atol=1e-7)
                    np.testing.assert_allclose(a['installation']['moment_cg_body_nm'], moment+np.cross(arm, force), rtol=1e-6, atol=1e-7)
                    for key in ('thrust_n', 'torque_nm', 'power_w', 'flap_cos_deg', 'flap_sin_deg'):
                        np.testing.assert_allclose(a['summary'][key], b['summary'][key], rtol=1e-6, atol=1e-8)

    def test_budget_trim_public_templates_and_history_replay(self):
        for name in list(designs.TEMPLATES)[:2]:
            legacy = designs.from_template(name)
            design = assembly.from_legacy(legacy)
            for analysis, speed in [('hover_budget', 0), ('trim', 0), ('trim', 15)]:
                with self.subTest(template=name, analysis=analysis, speed=speed):
                    case = dict(schema_version=3, model='helicopter', analysis=analysis, radial_stations=24,
                                altitude_m=0., requested_duration_s=600.)
                    if analysis == 'trim':
                        case.update(speed_m_s=speed, climb_m_s=0., azimuth_stations=24)
                    old, _ = designs.execute(legacy, case)
                    new, files = designs.execute(design, case)
                    self.assertEqual(old['status'], 'converged', old)
                    self.assertEqual(new['summary'], old['summary'])
                    self.assertIn('assembly.json', files)
            with TemporaryDirectory() as directory, patch.object(analysis_history, 'LIBRARY', Path(directory)/'history'):
                record = dict(answer=new, files=files, case=case, task='trim', context='trim', design=deepcopy(design),
                              input_fingerprint='test', fingerprint=designs.digest(design))
                identifier = analysis_history.save(record)
                design['aircraft']['mass_properties']['mass_kg'] *= 1.1
                restored = analysis_history.load(identifier)
                self.assertEqual(restored['design']['aircraft'], legacy['aircraft'])
                self.assertEqual(restored['answer']['summary'], new['summary'])
                root = Path(directory)/'relocated'
                for name, data in restored['files'].items():
                    path = root/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                replay = run_case(read_case(root/'case.json'), root, root/'replay')
                self.assertEqual(replay['summary'], new['summary'])

    def test_drive_ratio_updates_sweeps_and_rejects_conflicts(self):
        design = assembly.from_legacy(designs.from_template(next(iter(designs.TEMPLATES))))
        design['assembly']['instances'][1]['drive'] = dict(connection='powerplant', rpm_mode='main_ratio', ratio=7500/1700)
        assembly.refresh(design)
        self.assertFalse(designs.issues(design))
        aircraft = deepcopy(design['aircraft'])
        apply_design(aircraft, {'main_rpm': 1800.})
        self.assertAlmostEqual(aircraft['rotors'][1]['defaults']['rpm'], 1800*7500/1700)
        with self.assertRaisesRegex(ValueError, '冲突'):
            apply_design(aircraft, {'main_rpm': 1800., 'tail_rpm': 7500.})
        case = dict(schema_version=3, model='helicopter', analysis='hover_budget', radial_stations=24,
                    altitude_m=0., requested_duration_s=600.)
        result, files = designs.execute(design, case, dict(schema_version=1, kind='helicopter_sweep', axes={'main_rpm': [1700., 1800.]}))
        self.assertEqual(result['status'], 'converged', result)
        import json
        points = [json.loads(data) for name, data in files.items() if name.endswith('/aircraft.json')]
        self.assertEqual(len(points), 2)
        for aircraft in points:
            main, tail = aircraft['rotors']
            self.assertAlmostEqual(tail['defaults']['rpm'], main['defaults']['rpm']*7500/1700)


if __name__ == '__main__':
    unittest.main()
