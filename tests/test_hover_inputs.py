from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from rotordesignlab.aircraft import read_aircraft, require_analysis
from rotordesignlab.cases import write_json

ROOT = Path(__file__).resolve().parents[1]


class HoverInputsTest(unittest.TestCase):
    def test_templates_and_legacy(self):
        for name in ('synthetic','uh60-public'):
            aircraft = read_aircraft(ROOT/f'examples/hover/{name}.json')
            require_analysis(aircraft,'hover_budget')
            self.assertEqual({r['role'] for r in aircraft['rotors']},{'main','tail'})
        old = read_aircraft(ROOT/'examples/synthetic-aircraft.json')
        with self.assertRaisesRegex(ValueError,'版本 2'): require_analysis(old,'hover_budget')
        with self.assertRaisesRegex(ValueError,'缺少'): require_analysis(aircraft,'trim')
        with self.assertRaisesRegex(ValueError,'尚未实现'): require_analysis(aircraft,'linearize')

    def test_missing_fields_and_power_curves(self):
        data=read_aircraft(ROOT/'examples/hover/synthetic.json')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json'
            for change,expected in [
                (lambda a:a.pop('hover'),'hover'),
                (lambda a:a['rotors'][1].update(role='main'),'main'),
                (lambda a:a['rotors'][1].pop('transmission_efficiency'),'transmission_efficiency'),
                (lambda a:a['powerplant'].update(altitude_m=[0,0,6000,11000]),'递增'),
                (lambda a:a['powerplant'].update(short_time_power_w=[1,1,1,1]),'短时')]:
                copy=deepcopy(data);change(copy);write_json(path,copy)
                with self.assertRaisesRegex(ValueError,expected):read_aircraft(path)
            data['mass_properties'].pop('inertia_cg_kg_m2')
            write_json(path,data);read_aircraft(path)
