from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from rotordesignlab.batch import run_batch
from rotordesignlab.cases import read_case, write_json

ROOT=Path(__file__).resolve().parents[1]


class HoverBatchTest(unittest.TestCase):
    def test_offline_relocation_failures_and_limits(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);inputs=root/'inputs';shutil.copytree(ROOT/'examples/hover',inputs)
            spec=dict(schema_version=1,kind='helicopter_comparison',case_json='synthetic-case.json',variants=[
                dict(name='normal',overrides={}),dict(name='power insufficient',overrides=dict(mass_kg=230)),
                dict(name='unreachable',overrides=dict(mass_kg=900))])
            with patch('socket.socket.connect',side_effect=RuntimeError('offline test')):
                a=run_batch(spec,inputs,root/'a')
                self.assertEqual(a['summary'],dict(total=3,converged=2,failed=1,limit_violations=1),a)
                moved=root/'relocated';shutil.copytree(root/'a',moved)
                shutil.rmtree(inputs)
                b=run_batch(read_case(moved/'batch.json'),moved,root/'b')
            self.assertEqual(a['summary'],b['summary'])
            self.assertEqual((moved/'performance.csv').read_bytes(),(root/'b/performance.csv').read_bytes())
            self.assertFalse((root/'b/run.lock').exists())

    def test_sweeps_and_invalid_spec(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for i,axes in enumerate((dict(mass_kg=[180,200],altitude_m=[0,1000]),dict(tail_radius_m=[.24,.26],tail_arm_m=[1.7,1.9]))):
                a=run_batch(dict(schema_version=1,kind='helicopter_sweep',case_json='synthetic-case.json',axes=axes),ROOT/'examples/hover',root/str(i))
                self.assertEqual(a['summary']['total'],4);self.assertEqual(a['status'],'converged',a)
            for i,axes in enumerate((dict(mass_kg=[1,1]),dict(mass_kg=[True]),dict(cg_x=[1]),dict())):
                a=run_batch(dict(schema_version=1,kind='helicopter_sweep',case_json='synthetic-case.json',axes=axes),ROOT/'examples/hover',root/f'bad-{i}')
                self.assertEqual(a['status'],'failed');self.assertIn('error',a)
