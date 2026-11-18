from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from rotordesignlab import module_workspace as workspace
from rotordesignlab.cases import run_case, read_case
from rotordesignlab.batch import run_batch
from rotordesignlab import designs
from hashlib import sha256


class WorkspaceTests(unittest.TestCase):
    def test_migration_provenance_and_incomplete_import(self):
        design = designs.from_template(next(iter(designs.TEMPLATES)))
        original = designs.pack(design)
        draft = workspace.extract(original, design['aircraft']['rotors'][0]['id'])
        self.assertEqual(draft['migration']['source_sha256'], sha256(original).hexdigest())
        self.assertEqual(workspace.unpack(workspace.pack(draft)), draft)
        self.assertIn('rotor_to_body', draft['migration'])
        bad = deepcopy(draft)
        bad['case'].pop('flow_rotor_m_s')
        with self.assertRaises(ValueError):
            workspace.pack(bad)
        bad = deepcopy(draft)
        bad['sweep'] = dict(schema_version=1, kind='rotor_module_sweep', axes={'rpm': [1]*101})
        with self.assertRaises(ValueError):
            workspace.pack(bad)

    def test_roundtrip_conflict_history_trash_and_duplicate_names(self):
        draft = workspace.template(next(iter(workspace.TEMPLATES)))
        self.assertEqual(workspace.unpack(workspace.pack(draft)), draft)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, version = workspace.save(draft, library=root)
            second, _ = workspace.save(draft, library=root)
            self.assertNotEqual(first, second)
            self.assertEqual(len(workspace.saved(root)), 2)
            changed = deepcopy(draft)
            changed['case']['collective_deg'] = 14.
            _, new_version = workspace.save(changed, first, version, root)
            with self.assertRaisesRegex(ValueError, '另一窗口'):
                workspace.save(draft, first, version, root)
            old, _ = workspace.load(first, root, revision=version)
            self.assertEqual(old, draft)
            self.assertEqual(workspace.load(first, root)[0], changed)
            with self.assertRaises(ValueError):
                workspace.trash(first, version, root)
            self.assertFalse((root/(first+'.lock')).exists())
            workspace.trash(first, new_version, root)
            self.assertEqual(workspace.load(first, root, deleted=True)[0], changed)
            self.assertEqual(len(workspace.saved(root)), 1)
            workspace.save(changed, library=root)
            with self.assertRaises(ValueError):
                workspace.load('../bad', root)
            with self.assertRaises(ValueError):
                workspace.unpack(b'not a package')

    def test_execute_and_sweep_portable_replay_no_aircraft(self):
        draft = workspace.template(next(iter(workspace.TEMPLATES)))
        draft['case']['radial_stations'] = 24
        draft['case']['azimuth_stations'] = 12
        original = deepcopy(draft)
        with patch('rotordesignlab.aircraft.read_aircraft', side_effect=AssertionError('aircraft dependency')):
            result = workspace.execute(draft)
        self.assertEqual(draft, original)
        self.assertEqual(result['answer']['status'], 'converged', result['answer'])
        draft['case']['collective_deg'] = 14.
        self.assertNotEqual(result['fingerprint'], workspace.digest(draft))
        self.assertEqual(result['draft'], original)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in result['files'].items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            replay = run_case(read_case(root/'case.json'), root, root/'replay')
            self.assertEqual(replay['summary'], result['answer']['summary'])
            draft['sweep'] = dict(schema_version=1, kind='rotor_module_sweep',
                                  axes={'collective_deg': [12., 13.]})
            batch = workspace.execute(draft)
            self.assertEqual(batch['answer']['status'], 'converged', batch['answer'])
            for name, data in batch['files'].items():
                path = root/'batch'/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            replay = run_batch(read_case(root/'batch/batch.json'), root/'batch', root/'batch-replay')
            self.assertEqual(replay['rows'], batch['answer']['rows'])
            draft['sweep']['axes']['collective_deg'] = [12., 100.]
            failed = workspace.execute(draft)
            self.assertEqual(failed['answer']['status'], 'failed')
            self.assertEqual(failed['answer']['summary']['converged_points'], 1)
            self.assertIn('point-001/result.json', failed['files'])


if __name__ == '__main__':
    unittest.main()
