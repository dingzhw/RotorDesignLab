from copy import deepcopy
from io import BytesIO
import unittest
import numpy as np
import pandas as pd
from rotordesignlab.engineering_inputs import generate_geometry, scan_range, export_table, import_table, GEOMETRY, POLAR
from rotordesignlab.comparison_tables import export_candidates, import_candidates
from rotordesignlab import designs, module_workspace


class EngineeringInputsTests(unittest.TestCase):
    def test_step_boundaries_and_rejections(self):
        self.assertEqual(scan_range(0, .3, .1), [0., .1, .2, .3])
        self.assertEqual(scan_range(0, 1, .3), [0., .3, .6, .9])
        self.assertEqual(scan_range(3, 1, -1), [3., 2., 1.])
        self.assertEqual(scan_range(3, 3, 1), [3.])
        for values in [(0,1,0), (0,1,-1), (0,float('inf'),1), (0,1001,1), (1e18,1e18+1000,1)]:
            with self.assertRaises(ValueError):
                scan_range(*values)

    def test_geometry_and_local_pitch_definition(self):
        frame = generate_geometry(.2,.12,.06,12.,-4.,9,.75)
        self.assertEqual(frame.iloc[0].tolist(), [.2,.12,12.])
        self.assertEqual(frame.iloc[-1].tolist(), [1.,.06,-4.])
        local = np.interp(.75,frame.r_over_R,frame.twist_deg)
        self.assertAlmostEqual(10+local-local,10)
        self.assertAlmostEqual(np.trapezoid(frame.chord_m,frame.r_over_R), .8*.09)
        with self.assertRaises(ValueError):
            generate_geometry(.8,.1,.1,0.,0.,4,.75)

    def test_chinese_english_and_txt_roundtrip_and_row_errors(self):
        frame = generate_geometry(.2,.12,.06,12.,-4.,9,.75)
        for data in (export_table(frame,'工程估计'), frame.to_csv(index=False).encode(),
                     export_table(frame).decode('utf-8-sig').replace(',', '\t').encode('gb18030')):
            imported = import_table(data, GEOMETRY)
            np.testing.assert_array_equal(frame.to_numpy(), imported.to_numpy())
        bad = '半径比 r/R,实际弦长 / m,几何扭转 / °\n0.2,0.1,0\n1,未知,0\n'.encode()
        with self.assertRaisesRegex(ValueError, '第3行.*实际弦长'):
            import_table(bad, GEOMETRY)
        for text in ('r_over_R,chord_m,twist_deg\n.2,.1,0\n.2,.1,0',
                     'r_over_R,chord_m,twist_deg\n.2,.1,0\n1,-.1,0',
                     'r_over_R,chord_m,twist_deg\n.2,.1,0\n1,nan,0'):
            with self.assertRaises(ValueError):
                import_table(text.encode(), GEOMETRY)

    def test_generated_module_calculation_and_roundtrip(self):
        draft = module_workspace.template(next(iter(module_workspace.TEMPLATES)))
        saved_mass = deepcopy(draft['module']['blade_mass'])
        frame = generate_geometry(.2,.12,.08,10.,-4.,6,.75)
        draft['assets']['geometry.csv'] = frame.to_csv(index=False).encode()
        draft['case'].update(radial_stations=24, azimuth_stations=12)
        original = module_workspace.execute(draft)
        self.assertEqual(original['answer']['status'], 'converged', original['answer'])
        draft['assets']['geometry.csv'] = import_table(export_table(frame,'参数化估算'), GEOMETRY).to_csv(index=False).encode()
        restored = module_workspace.unpack(module_workspace.pack(draft))
        result = module_workspace.execute(restored)
        self.assertEqual(result['answer']['summary'], original['answer']['summary'])
        self.assertEqual(restored['module']['blade_mass'], saved_mass)

    def test_candidate_table_and_naming_compatibility(self):
        items = [dict(name=f'方案{i}', main_radius_m=1.1, main_rpm=1700., tail_radius_m=.24,
                      tail_arm_m=1.7,cg_x_m=0.,geometry_rule='preserve_chord',provenance='估计') for i in range(3)]
        self.assertEqual(import_candidates(export_candidates(items)),items)
        with self.assertRaises(ValueError):
            import_candidates(b'')
        with self.assertRaises(ValueError):
            import_candidates(export_candidates(items[:2]))
        old = designs.from_template('200 kg 合成无人直升机')
        new = designs.from_template('千机-200轻型无人直升机')
        self.assertEqual(old,new)
        new['aircraft']['name'] = '用户历史方案名称'
        self.assertEqual(designs.unpack(designs.pack(new))['aircraft']['name'],'用户历史方案名称')

    def test_polar_layer_roundtrip_keeps_separate_domain(self):
        frame = pd.DataFrame({'alpha_deg':[-10.,0.,10.], 'Ma=0':[0.,1.,2.], 'Ma=0.3':[.1,1.1,2.1]})
        restored = import_table(export_table(frame,'独立高攻角分支留在原表'),list(frame.columns))
        np.testing.assert_array_equal(restored.to_numpy(),frame.to_numpy())
        with self.assertRaises(ValueError):
            import_table(b'alpha_deg,cl,cd\n-10,-1,-.1\n10,1,.1',POLAR)


if __name__ == '__main__':
    unittest.main()
