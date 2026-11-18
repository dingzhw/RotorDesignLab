from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import unittest
import numpy as np
from rotordesignlab import designs, assembly
from rotordesignlab.batch import run_batch
from rotordesignlab.cases import run_case, read_case, write_json
from rotordesignlab.design_comparison import prepare_candidate, design_parameters


def variants():
    return [dict(name=name, overrides=changes, geometry_rule='preserve_chord', provenance='合成敏感性输入；非实测机型')
            for name, changes in [('基准', {}), ('加大主桨', {'main_radius_m':1.155}), ('降低转速', {'main_rpm':1615.})]]


class DesignComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.design = assembly.from_legacy(designs.from_template('200 kg 合成无人直升机'))
        path = designs.materialize(self.design, self.root/'base')
        self.case = dict(schema_version=3, model='helicopter', analysis='trim', aircraft_json=str(path),
                         altitude_m=0., speed_m_s=0., climb_m_s=0., requested_duration_s=600.,
                         radial_stations=24, azimuth_stations=12)
        write_json(self.root/'case.json', self.case)
        self.spec = dict(schema_version=1, kind='helicopter_design_comparison', case_json='case.json', variants=variants())

    def test_same_task_margins_and_portable_replay(self):
        before = deepcopy(self.design)
        answer = run_batch(self.spec, self.root, self.root/'first')
        self.assertEqual(answer['status'], 'converged', answer)
        original = run_case(self.case, self.root, self.root/'original')
        self.assertEqual(answer['candidates'][0]['result']['summary'], original['summary'])
        for item in answer['candidates']:
            self.assertEqual(item['parameters']['飞行质量_kg'], 200.)
            saved = read_case(self.root/'first'/item['directory']/'run/case.json')
            for key in ('speed_m_s','altitude_m','climb_m_s','requested_duration_s'):
                self.assertEqual(saved[key], self.case[key])
            summary = item['result']['summary']
            margins = item['result']['control_margins_deg']
            aircraft = read_case(self.root/'first'/item['directory']/'run/aircraft.json')
            low, high = aircraft['rotors'][0]['limits']['collective_deg']
            self.assertAlmostEqual(margins['main_collective_deg']['to_lower'], summary['main_collective_deg']-low)
            self.assertAlmostEqual(margins['main_collective_deg']['to_upper'], high-summary['main_collective_deg'])
        shutil.copytree(self.root/'first', self.root/'moved')
        replay = run_batch(read_case(self.root/'moved/batch.json'), self.root/'moved', self.root/'replay')
        for a, b in zip(answer['candidates'], replay['candidates']):
            self.assertEqual(a['result']['summary'], b['result']['summary'])
        self.assertEqual(self.design, before)
        self.assertNotIn('error', answer)

    def test_failed_candidate_and_task_override_rejection(self):
        self.spec['variants'][1]['overrides'] = {'main_radius_m':.03}
        answer = run_batch(self.spec, self.root, self.root/'partial')
        self.assertEqual(answer['status'], 'partial', answer)
        failed = answer['candidates'][1]['result']
        self.assertNotIn('summary', failed)
        self.assertTrue(failed['error'])
        self.spec['variants'][1]['overrides'] = {'altitude_m':3000.}
        rejected = run_batch(self.spec, self.root, self.root/'reject')
        self.assertEqual(rejected['status'], 'failed')
        self.assertIn('任务条件', rejected['error'])

    def test_geometry_rules_and_unchanged_mass_moments(self):
        aircraft = self.design['aircraft']
        base = self.root/'base'
        original = design_parameters(aircraft, base)
        for rule in ('preserve_chord','preserve_solidity'):
            folder = self.root/rule
            folder.mkdir()
            change = dict(name='试验', overrides={'main_radius_m':1.21}, geometry_rule=rule, provenance='合成')
            candidate = prepare_candidate(aircraft, base, folder, change)
            sigma = design_parameters(candidate, folder)['主桨实度']
            expected = original['主桨实度'] if rule=='preserve_solidity' else original['主桨实度']/1.1
            self.assertAlmostEqual(sigma, expected)
            self.assertEqual(candidate['mass_properties'], aircraft['mass_properties'])
            self.assertEqual(candidate['rotors'][0]['flight'], aircraft['rotors'][0]['flight'])
        from tools.build_a2_example import synthetic
        dynamic = synthetic()['aircraft']
        folder = self.root/'coupled'
        folder.mkdir()
        with self.assertRaisesRegex(ValueError, '质量分账'):
            prepare_candidate(dynamic, base, folder, change)

    def test_cg_and_tail_arm_share_the_new_reference(self):
        folder = self.root/'changed-cg'
        folder.mkdir()
        change = dict(name='重心及力臂', overrides={'cg_x_m':.1, 'tail_arm_m':2.5},
                      geometry_rule='preserve_chord', provenance='合成几何检查')
        candidate = prepare_candidate(self.design['aircraft'], self.root/'base', folder, change)
        tail = next(r for r in candidate['rotors'] if r['role'] == 'tail')
        self.assertAlmostEqual(tail['position_m'][0], -2.4)
        self.assertAlmostEqual(design_parameters(candidate, folder)['尾桨纵向力臂_m'], 2.5)

    def test_failed_all_and_nonfinite_inputs_preserve_diagnostics(self):
        for item in self.spec['variants']:
            item['overrides'] = {'main_radius_m':.03}
        answer = run_batch(self.spec, self.root, self.root/'all-failed')
        self.assertEqual(answer['status'], 'failed')
        self.assertEqual(answer['summary']['failed'], 3)
        self.assertTrue((self.root/'all-failed/report.md').exists())
        self.spec['variants'][0]['overrides'] = {'main_rpm':float('nan')}
        rejected = run_batch(self.spec, self.root, self.root/'nonfinite')
        self.assertEqual(rejected['status'], 'failed')
        self.assertTrue((self.root/'nonfinite/result.json').exists())
        self.assertFalse((self.root/'nonfinite/run.lock').exists())

    def test_failed_report_is_not_claimed_as_complete(self):
        from unittest.mock import patch
        with patch('rotordesignlab.design_comparison_report.render', side_effect=OSError('导出写入失败')):
            result = run_batch(self.spec, self.root, self.root/'export-failed')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(result['candidates']), 3)
        self.assertIn('导出写入失败', result['error'])


if __name__ == '__main__':
    unittest.main()
