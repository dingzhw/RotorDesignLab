from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import shutil
import numpy as np
from rotordesignlab.batch import run_batch
from rotordesignlab.cases import read_case,run_case

ROOT=Path(__file__).resolve().parents[1]


class TrimBatchTest(unittest.TestCase):
    def test_continuation_partial_replay_and_offline(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp);spec=dict(schema_version=1,kind='helicopter_trim_sweep',case_json='synthetic-case.json',
                axes={'speed_m_s':[0,10,40]},continuation=True)
            with patch('socket.socket.connect',side_effect=AssertionError('Offline check')):
                r=run_batch(spec,ROOT/'examples/trim',base/'batch')
                self.assertEqual(r['status'],'partial',r);self.assertEqual(r['summary']['converged'],2)
                failed=read_case(base/'batch/point-0002/result.json')
                self.assertEqual(failed['solver_status'],'not_converged')
                self.assertEqual(failed['support_status'],'not_established')
                self.assertIn('alpha_min_deg',failed['diagnostics']['rotors']['main'])
                original=read_case(base/'batch/point-0001/result.json');snapshot=read_case(base/'batch/point-0001/case.json')
                self.assertEqual(len(snapshot['initial_state']),18)
                shutil.copytree(base/'batch/point-0001',base/'moved')
                replay=run_case(snapshot,base/'moved',base/'replay')
                self.assertEqual(replay['summary'],original['summary'])
                other=run_case({k:v for k,v in snapshot.items() if k!='initial_state'},base/'moved',base/'independent')
                np.testing.assert_allclose(list(other['summary'].values()),list(original['summary'].values()),atol=1e-5,rtol=1e-7)
                for name in ('performance.png','performance.svg','controls.png','report.md'):
                    self.assertGreater((base/'batch'/name).stat().st_size,50)
                public=read_case(ROOT/'examples/trim/uh60-public-case.json')
                domain=run_case(dict(public,speed_m_s=30),ROOT/'examples/trim',base/'domain')
                self.assertEqual(domain['status'],'failed')
                self.assertEqual(domain['solver_status'],'converged')
                self.assertEqual(domain['support_status'],'outside_implemented_domain')

    def test_invalid_scan_and_seed(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp);spec=dict(schema_version=1,kind='helicopter_trim_sweep',case_json='synthetic-case.json',axes={'speed_m_s':[0,0]})
            r=run_batch(spec,ROOT/'examples/trim',base/'invalid');self.assertEqual(r['status'],'failed')
            case=read_case(ROOT/'examples/trim/synthetic-case.json');case['initial_state']=[True]*18
            r=run_case(case,ROOT/'examples/trim',base/'seed');self.assertEqual(r['status'],'failed');self.assertIn('initial_state',r['error'])
