from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import unittest
import numpy as np
from rotordesignlab import designs, assembly
from rotordesignlab.cases import run_case, read_case, write_json
from rotordesignlab.power_accounting import ledger


class PowerAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.design = assembly.from_legacy(designs.from_template('200 kg 合成无人直升机'))
        self.path = designs.materialize(self.design, self.root/'inputs')
        self.case = dict(schema_version=3, model='helicopter', analysis='hover_comparison',
                         aircraft_json=str(self.path), altitude_m=0., requested_duration_s=600.,
                         radial_stations=24, azimuth_stations=12)

    def test_compare_relocation_replay_and_power_closure(self):
        answer = run_case(self.case, self.root, self.root/'first')
        self.assertEqual(answer['status'], 'converged', answer)
        for item in answer['methods'].values():
            ledger_ = item['power_accounting']
            self.assertLess(abs(ledger_['sum_residual_w']), 1e-7)
            self.assertLess(abs(ledger_['margin_residual_w']), 1e-7)
            self.assertTrue(all(abs(r['omega_q_residual_w']) < 1e-7 for r in ledger_['components']))
        shutil.copytree(self.root/'first', self.root/'moved')
        replay = run_case(read_case(self.root/'moved/case.json'), self.root/'moved', self.root/'replay')
        self.assertEqual(replay['status'], 'converged')
        for key in answer['methods']:
            self.assertEqual(answer['methods'][key]['summary'], replay['methods'][key]['summary'])
            self.assertEqual(answer['methods'][key]['power_accounting'], replay['methods'][key]['power_accounting'])

    def test_efficiency_accessory_and_rating_boundary(self):
        result = run_case(self.case, self.root, self.root/'reference')['methods']['hover_budget']
        aircraft = deepcopy(self.design['aircraft'])
        main, tail = aircraft['rotors']
        main['transmission_efficiency'] = .8
        tail['transmission_efficiency'] = 1.
        for r in aircraft['rotors']:
            r['defaults']['rpm'] = 30/np.pi
        aircraft['powerplant'].update(accessory_power_w=1000., continuous_power_w=[4000.]*4,
                                     short_time_power_w=[6000.]*4, short_time_duration_s=300.)
        summary = result['summary']
        summary.update(main_power_w=2000., tail_power_w=500., main_torque_nm=2000., tail_torque_nm=500.,
                       required_power_w=4000., duration_margin_w=2000.)
        for duration, selected in [(300., 6000.), (300.001, 4000.)]:
            summary['duration_margin_w'] = selected-4000
            values = ledger(aircraft, dict(self.case, requested_duration_s=duration), result)
            self.assertEqual(values['selected_available_w'], selected)
            self.assertAlmostEqual(values['sum_residual_w'], 0.)
            self.assertEqual(values['components'][0]['loss_w'], 500.)
            self.assertEqual(values['components'][1]['loss_w'], 0.)

    def test_partial_failure_preserves_successful_method(self):
        aircraft = read_case(self.path)
        aircraft['rotors'][0]['flight']['x_reference_body'] = aircraft['rotors'][0]['thrust_axis_body']
        write_json(self.path, aircraft)
        result = run_case(self.case, self.root, self.root/'partial')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['methods']['hover_budget']['status'], 'converged')
        self.assertEqual(result['methods']['trim']['status'], 'failed')
        self.assertIsNone(result['power_feasibility_depends_on_method'])

    def test_power_disagreement_is_explicit(self):
        aircraft = read_case(self.path)
        aircraft['powerplant']['continuous_power_w'] = [41000.]*4
        aircraft['powerplant']['short_time_power_w'] = [55000.]*4
        write_json(self.path, aircraft)
        result = run_case(self.case, self.root, self.root/'disagree')
        self.assertEqual(result['status'], 'converged')
        self.assertTrue(result['power_feasibility_depends_on_method'])
        self.assertIn('依赖模型假设', result['warnings'][0])


if __name__ == '__main__':
    unittest.main()
