from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import numpy as np

from rotordesignlab import rotor_module as rm
from rotordesignlab.cases import read_case, write_json, run_case
from rotordesignlab import designs

ROOT = Path(__file__).resolve().parents[1]


class ModuleTests(unittest.TestCase):
    def make(self, root, role='main', public=False):
        source = ROOT / ('examples/public-helicopter/uh60-public.json' if public else 'examples/templates/v045/synthetic.json')
        rm.extract(source, role, root/'module')
        return source, read_case(root/'module/case.json')

    def test_independent_relocated_package_replay_and_invalid_fields(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _, case = self.make(root)
            module, assets = rm.load(root/'module/module.json')
            self.assertNotIn('mass_properties', module)
            self.assertNotIn('position_m', module['rotor'])
            for mode in ('fixed','module'):
                with patch('rotordesignlab.aircraft.read_aircraft', side_effect=AssertionError('aircraft dependency')):
                    result = run_case(dict(case,flapping_model=mode),root/'module',root/("run-"+mode))
                self.assertEqual(result['status'],'converged',result)
                replay = run_case(read_case(root/("run-"+mode)/'case.json'),root/("run-"+mode),root/(mode+'-replay'))
                self.assertEqual(result['summary'],replay['summary'])
            package = root/'portable.rdlr'
            rm.save(module, assets, package)
            self.assertEqual(rm.load(package),(module,assets))
            packed = run_case(dict(case,module_file='portable.rdlr'),root,root/'packed')
            self.assertEqual(packed['summary'],result['summary'])
            target = run_case(dict(case, target={'solve_for':'collective_deg',
                              'thrust_n':result['summary']['thrust_n']}), root/'module',root/'target')
            self.assertEqual(target['status'],'converged',target)
            self.assertLess(target['target_solution']['relative_thrust_error'],1e-6)
            with self.assertRaises(FileExistsError):
                rm.save(module, assets, package)
            invalid = deepcopy(module)
            invalid['mass_properties'] = {'mass_kg':1}
            with self.assertRaises(ValueError):
                rm.validate(invalid)
            invalid = deepcopy(module)
            invalid['rotor']['geometry_csv']='../outside.csv'
            with self.assertRaises(ValueError):
                rm.validate(invalid)
            invalid = deepcopy(module)
            invalid['blade_mass']['mass_kg']=.01
            with self.assertRaises(ValueError):
                rm.validate(invalid)

    def test_legacy_body_to_local_loads_and_gravity_main_tail(self):
        for role in ('main','tail'):
            with self.subTest(role=role), TemporaryDirectory() as temp:
                root = Path(temp)
                source, reference = self.make(root,role,public=True)
                before = source.read_bytes()
                migration = read_case(root/'module/migration.json')
                basis = np.array(migration['rotor_to_body'])
                local_flow = np.array([8.,2.,-1.])
                old = dict(schema_version=2,model='spatial_rotor',aircraft_json=str(source),rotor_id=role,
                           rpm=reference['rpm'],collective_deg=reference['collective_deg'],radial_stations=32,
                           azimuth_stations=36,flow_body_m_s=(basis@local_flow).tolist(),attitude_deg=[8.,-4.],
                           flapping_model='aircraft',cyclic_cos_deg=.1,cyclic_sin_deg=-.1,environment=reference['environment'])
                converted = rm.convert_case(old,migration,reference)
                a = run_case(old,source.parent,root/'old')
                b = run_case(converted,root/'module',root/'new')
                self.assertEqual(a['status'],'converged',a)
                self.assertEqual(b['status'],'converged',b)
                for key in ('thrust_n','torque_nm','power_w','flap_coning_deg','flap_cos_deg','flap_sin_deg'):
                    np.testing.assert_allclose(a['summary'][key],b['summary'][key],rtol=1e-6,atol=1e-8)
                np.testing.assert_allclose(a['installation']['force_rotor_n'],b['force_rotor_n'],rtol=1e-6,atol=1e-7)
                np.testing.assert_allclose(a['installation']['moment_hub_rotor_nm'],b['moment_hub_rotor_nm'],rtol=1e-6,atol=1e-7)
                self.assertEqual(source.read_bytes(),before)

    def test_stiffness_damping_missing_mass_and_axial(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            _, case=self.make(root)
            folder=root/'module'
            module=read_case(folder/'module.json')
            case.update(flow_rotor_m_s=[10.,0.,-1.],cyclic_cos_deg=.5)
            baseline=run_case(case,folder,root/'baseline')
            self.assertEqual(baseline['status'],'converged',baseline)
            for field,value in [('spring_nm_rad',50.),('damper_nms_rad',5.)]:
                changed=deepcopy(module)
                changed['flapping'][field]=value
                write_json(folder/'module.json',changed)
                result=run_case(case,folder,root/field)
                self.assertEqual(result['status'],'converged',result)
                self.assertGreater(abs(result['summary']['flap_cos_deg']-baseline['summary']['flap_cos_deg']),1e-5)
            missing=deepcopy(module)
            missing['blade_mass'].pop('inertia_kg_m2')
            write_json(folder/'module.json',missing)
            failure=run_case(case,folder,root/'missing')
            self.assertEqual(failure['status'],'failed')
            self.assertIn('inertia_kg_m2',failure['error'])
            write_json(folder/'module.json',module)
            axial=dict(case,method='axial',flapping_model='fixed',flow_rotor_m_s=[0.,0.,0.],cyclic_cos_deg=0.)
            a=run_case(axial,folder,root/'axial')
            self.assertEqual(a['status'],'converged',a)
            inverse=run_case(dict(axial,target={'solve_for':'collective_deg','thrust_n':a['summary']['thrust_n']}),folder,root/'inverse')
            self.assertEqual(inverse['status'],'converged',inverse)
            self.assertLess(inverse['target_solution']['relative_thrust_error'],1e-6)
            invalid=run_case(dict(axial,flow_rotor_m_s=[1.,0.,0.]),folder,root/'invalid-axial')
            self.assertEqual(invalid['status'],'failed')

    def test_rdl_extraction_and_package_tamper(self):
        from io import BytesIO
        from zipfile import ZipFile
        with TemporaryDirectory() as temp:
            root=Path(temp)
            original=designs.pack(designs.from_template(next(iter(designs.TEMPLATES))))
            (root/'old.rdl').write_bytes(original)
            rm.extract(root/'old.rdl','main',root/'module')
            self.assertEqual((root/'old.rdl').read_bytes(),original)
            stream=BytesIO()
            with ZipFile(root/'module/module.rdlr') as source, ZipFile(stream,'w') as target:
                for name in source.namelist():
                    target.writestr(name,source.read(name)+(b'\n' if name=='geometry.csv' else b''))
            with self.assertRaisesRegex(ValueError,'哈希'):
                rm.unpack(stream.getvalue())


if __name__=='__main__':
    unittest.main()
