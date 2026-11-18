"""Offline payload integrity and replay of real exported input, not mocked solvers."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from offline_check import verify
from replay_results import replay
from rotordesignlab import module_workspace


class OfflineDeliveryTests(unittest.TestCase):
    def test_manifest_detects_changed_missing_and_external_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'a.txt').write_bytes(b'original')
            manifest = dict(files={'a.txt': sha256(b'original').hexdigest()})
            (root/'distribution-manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(verify(root), [])
            (root/'a.txt').write_bytes(b'changed')
            self.assertIn('内容不符', verify(root)[0])
            (root/'a.txt').unlink()
            self.assertIn('缺失', verify(root)[0])
            manifest['files']['../outside'] = 'anything'
            (root/'distribution-manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(len(verify(root)), 2)

    def test_module_and_sweep_exports_replay_without_aircraft(self):
        draft = module_workspace.template(next(iter(module_workspace.TEMPLATES)))
        draft['case']['radial_stations'] = 24
        draft['case']['azimuth_stations'] = 12
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, sweep in enumerate((None, dict(schema_version=1, kind='rotor_module_sweep',
                                                     axes={'collective_deg': [12., 13.]}))):
                draft['sweep'] = sweep
                result = module_workspace.execute(draft)
                archive = root/f'export-{index}.zip'
                archive.write_bytes(module_workspace.archive(result['files']))
                original = sha256(archive.read_bytes()).hexdigest()
                checked = replay(archive, root/f'replay-{index}')
                self.assertEqual(checked['status'], 'converged', checked)
                self.assertTrue(checked['summary_exactly_equal'], checked)
                self.assertEqual(original, sha256(archive.read_bytes()).hexdigest())
                with self.assertRaises(FileExistsError):
                    replay(archive, root/f'replay-{index}')

    def test_replay_rejects_unsafe_paths_duplicates_and_external_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = [
                {'../escape.txt': b'x'},
                {'A.txt': b'x', 'a.txt': b'y'},
                {'bad./x': b'x'},
                {'case.json': json.dumps(dict(model='aircraft_rotor', aircraft_json='../outside.json')).encode()},
                {'case.json': b'{"model":"uh60"}'},
                {'design.rdl': b'not a result'},
            ]
            for index, files in enumerate(invalid):
                archive = root/f'invalid-{index}.zip'
                with ZipFile(archive, 'w') as stream:
                    for name, data in files.items():
                        stream.writestr(name, data)
                with self.assertRaises(ValueError):
                    replay(archive, root/f'out-{index}')
            self.assertFalse((root/'escape.txt').exists())


if __name__ == '__main__':
    unittest.main()
