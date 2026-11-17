from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from unittest.mock import patch
import pandas as pd

from rotordesignlab import designs
from rotordesignlab.design_models import AXIAL, SPATIAL, rotor_model
from rotordesignlab.engineering_display import result_table
from rotordesignlab.cases import run_case

ROOT = Path(__file__).resolve().parents[1]


def historic_package(design, settings):
    """Build historical bytes without the current producer's normalization."""
    stream = BytesIO()
    with ZipFile(BytesIO(designs.pack(design))) as old, ZipFile(stream, 'w') as new:
        manifest = json.loads(old.read('design.json'))
        manifest['settings'] = settings
        new.writestr('design.json', json.dumps(manifest))
        for name in old.namelist():
            if name != 'design.json':
                new.writestr(name, old.read(name))
    return stream.getvalue()


class CloseoutTests(unittest.TestCase):
    def test_historical_semantics_and_ambiguous_roundtrip(self):
        design = designs.from_template(next(iter(designs.TEMPLATES)))
        samples = [({}, AXIAL), ({'_workspace_revision': 3}, None),
                   ({'_workspace_revision': 3, 'rotor': {'flow_model': AXIAL}}, AXIAL),
                   ({'_workspace_revision': 3, 'rotor': {'flow_model': SPATIAL}}, SPATIAL),
                   ({'_workspace_revision': 3, '_last_rotor_case': {'model': 'aircraft_rotor'}}, AXIAL),
                   ({'_workspace_revision': 3, '_last_rotor_case': {'model': 'spatial_rotor'}}, SPATIAL),
                   ({'_workspace_revision': 6}, SPATIAL)]
        for settings, expected in samples:
            raw = historic_package(design, settings)
            restored = designs.unpack(raw)
            self.assertEqual(rotor_model(restored['settings']), expected)
            reopened = designs.unpack(designs.pack(restored))
            self.assertEqual(rotor_model(reopened['settings']), expected)
            self.assertEqual(restored['aircraft'], design['aircraft'])
            self.assertIn('_producer_version', reopened['settings'])
            self.assertEqual(designs.unpack(raw)['settings'], restored['settings'])

    def test_composite_labels_and_unknown_values(self):
        original = pd.DataFrame({'dominant_states': ['theta:0.5441; tail_lambdac:0.0123; future:0.0001', None]})
        translated = result_table(original)
        value = translated.iloc[0, 0]
        self.assertIn('俯仰', value)
        self.assertIn('尾桨', value)
        self.assertIn('future:0.0001', value)
        self.assertIn('0.5441', value)
        self.assertEqual(original.iloc[0, 0].split(':')[0], 'theta')
        self.assertTrue(pd.isna(translated.iloc[1, 0]))

    def test_diagnostic_flag_does_not_change_physics_and_cli_exit(self):
        from rotordesignlab.__main__ import main
        design = designs.from_template(next(iter(designs.TEMPLATES)))
        case = dict(schema_version=3, model='helicopter', analysis='linearize',
                    altitude_m=0, speed_m_s=0, climb_m_s=0, requested_duration_s=180,
                    radial_stations=24, azimuth_stations=24)
        first, files = designs.execute(design, case)
        second, other = designs.execute(design, dict(case, diagnostic_only=True))
        self.assertEqual(first['status'], 'converged', first)
        self.assertEqual(first['evaluation_restriction']['issue'], 'R19')
        self.assertFalse(first['evaluation_restriction']['engineering_use_allowed'])
        self.assertEqual(files['A.csv'], other['A.csv'])
        self.assertEqual(files['B.csv'], other['B.csv'])
        self.assertIn('交叉耦合待修复', files['report.md'].decode())
        self.assertIn('交叉耦合待修复', files['modes.svg'].decode())
        for result, code in [(first, 3), (second, 0)]:
            with patch('sys.argv', ['rotordesignlab', 'run', 'case.json', '--out', 'out']), \
                 patch('rotordesignlab.__main__.read_case', return_value=case), \
                 patch('rotordesignlab.__main__.run_case', return_value=result), \
                 patch('sys.stdout'), patch('sys.stderr'):
                self.assertEqual(main(), code)


if __name__ == '__main__':
    unittest.main()
