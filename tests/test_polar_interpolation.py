from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from rotordesignlab.cases import read_case, read_rotor, run_case, write_json
from rotordesignlab import rotor_module as rm, assembly, designs
from rotordesignlab.model_scope import open_loop_restriction
from tools.build_a2_example import synthetic

ROOT = Path(__file__).resolve().parents[1]


class PolarInterpolationTests(unittest.TestCase):
    def test_candidate_keeps_engineering_restriction(self):
        design = synthetic()
        aircraft = design['aircraft']
        aircraft['rotors'][0]['polar_interpolation'] = 'pchip_alpha_v1'
        restriction = open_loop_restriction(aircraft)
        self.assertFalse(restriction['engineering_use_allowed'])
        self.assertIn('连续斜率插值候选', restriction['note'])
        self.assertIn('尚未闭合', restriction['note'])

    def model(self):
        case = read_case(ROOT/'examples/three-blade.json')
        return read_rotor(case, ROOT/'examples')[0]

    def test_legacy_lookup_is_identical(self):
        model = self.model()
        alpha = np.linspace(model.polar[0, 0]-1, model.polar[-1, 0]+1, 201)
        for i, value in enumerate(model.polar_coefficients(alpha)):
            np.testing.assert_array_equal(value, np.interp(alpha, model.polar[:, 0], model.polar[:, i+1]))

    def test_nodes_shape_and_continuous_internal_derivatives(self):
        model = replace(self.model(), polar_interpolation='pchip_alpha_v1')
        nodes = model.polar[:, 0]
        np.testing.assert_allclose(np.array(model.polar_coefficients(nodes)).T, model.polar[:, 1:], atol=1e-14)
        for left, right, values in zip(nodes[:-1], nodes[1:], zip(model.polar[:-1, 1:], model.polar[1:, 1:])):
            curve = np.array(model.polar_coefficients(np.linspace(left, right, 31))).T
            self.assertTrue(np.all(curve >= np.minimum(*values)-1e-14))
            self.assertTrue(np.all(curve <= np.maximum(*values)+1e-14))
            self.assertTrue(np.all(curve[:, 1] >= 0))
        derivative = model._polar_curve.derivative()
        np.testing.assert_allclose(derivative(nodes[1:-1]-1e-7), derivative(nodes[1:-1]+1e-7), atol=1e-6)
        with self.assertRaises(ValueError):
            model.polar_coefficients([nodes[-1]+1], strict=True)
        with self.assertRaises(ValueError):
            replace(model, airfoil_grid=object())

    def test_module_and_assembly_preserve_explicit_choice_and_replay(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            rm.extract(ROOT/'examples/templates/v045/synthetic.json', 'main', root/'module')
            module, assets = rm.load(root/'module/module.json')
            module['rotor']['polar_interpolation'] = 'pchip_alpha_v1'
            np.testing.assert_equal(rm.unpack(rm.pack(module, assets))[0], module)
            write_json(root/'module/module.json', module)
            case = read_case(root/'module/case.json')
            result = run_case(case, root/'module', root/'first')
            self.assertEqual(result['status'], 'converged', result)
            replay = run_case(read_case(root/'first/case.json'), root/'first', root/'replay')
            self.assertEqual(result['summary'], replay['summary'])
            design = designs.from_template('200 kg 合成无人直升机')
            for rotor in design['aircraft']['rotors']:
                rotor['polar_interpolation'] = 'pchip_alpha_v1'
            installed = assembly.from_legacy(design)
            self.assertTrue(all(r['polar_interpolation']=='pchip_alpha_v1' for r in installed['aircraft']['rotors']))


if __name__ == '__main__':
    unittest.main()
