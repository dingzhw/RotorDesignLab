from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from rotordesignlab import designs
from rotordesignlab.cases import run_case
from rotordesignlab.parameter_fields import FIELDS, INTERNAL
from rotordesignlab.aircraft import SCHEMA_V2


class DesignTests(unittest.TestCase):
    def test_dictionary_covers_model_schema(self):
        def check(schema):
            for key,value in schema.get('properties',{}).items():
                self.assertTrue(key in FIELDS or key in INTERNAL,key)
                check(value)
                check(value.get('items',{}))
        check(SCHEMA_V2)

    def test_template_roundtrip_all_assets_and_settings(self):
        for name in designs.TEMPLATES:
            d=designs.from_template(name);d['settings']['trim']={'speed_m_s':20.,'radial_stations':40}
            self.assertEqual(designs.issues(d),[])
            self.assertEqual(designs.unpack(designs.pack(d)),d)

    def test_save_reopen_history_and_conflict(self):
        with TemporaryDirectory() as directory:
            d=designs.from_template(next(iter(designs.TEMPLATES)))
            identifier,version=designs.save_design(d,library=directory)
            self.assertEqual(designs.load_design(identifier,directory)[0],d)
            original=deepcopy(d);d['aircraft']['name']='重开方案 中文';d['aircraft']['mass_properties']['mass_kg']=205.
            _,new=designs.save_design(d,identifier,version,directory)
            self.assertNotEqual(new,version)
            self.assertEqual(designs.saved_designs(directory),[(identifier,'重开方案 中文')])
            backup=next((Path(directory)/'history').glob('*.rdl'))
            self.assertEqual(designs.unpack(backup.read_bytes()),original)
            with self.assertRaisesRegex(ValueError,'另一窗口'):designs.save_design(original,identifier,version,directory)
            self.assertEqual(designs.load_design(identifier,directory)[0],d)
            new_id,_=designs.save_design(d,library=directory);self.assertNotEqual(new_id,identifier)

    def test_invalid_archive_and_field_diagnostics(self):
        d=designs.from_template(next(iter(designs.TEMPLATES)))
        d['aircraft']['rotors'][0]['radius_m']=-1
        d['aircraft']['mass_properties']['mass_kg']=None
        errors='\n'.join(designs.issues(d))
        self.assertIn('旋翼半径',errors);self.assertIn('整机质量',errors)
        with self.assertRaises(ValueError):designs.pack(d)
        with self.assertRaises(ValueError):designs.unpack(b'not a zip')
        d=designs.from_template(next(iter(designs.TEMPLATES)))
        d['assets']['../../outside.csv']='data'
        with self.assertRaisesRegex(ValueError,'数据表名称'):designs.pack(d)

    def test_analysis_completeness_and_inertia(self):
        d=designs.from_template(next(iter(designs.TEMPLATES)))
        del d['aircraft']['mass_properties']['inertia_cg_kg_m2']
        self.assertEqual(designs.issues(d,'hover_budget'),[])
        self.assertIn('惯量','\n'.join(designs.issues(d,'linearize')))
        d['aircraft']['mass_properties']['inertia_cg_kg_m2']=[[1,2,0],[0,1,0],[0,0,1]]
        self.assertIn('对称','\n'.join(designs.issues(d)))

    def test_relocation_and_numerical_replay(self):
        for name in list(designs.TEMPLATES)[:2]:
            d=designs.from_template(name)
            with TemporaryDirectory() as temporary:
                root=Path(temporary);path=designs.materialize(designs.unpack(designs.pack(d)),root/'搬移 后')
                case=dict(schema_version=3,model='helicopter',analysis='hover_budget',altitude_m=0,
                          requested_duration_s=600,radial_stations=32)
                before=run_case(dict(case,aircraft_json=str(designs.TEMPLATES[name])),root,root/'original')
                after=run_case(dict(case,aircraft_json=str(path)),root,root/'reopened')
                self.assertEqual(before['status'],'converged',before)
                self.assertEqual(before['summary'],after['summary'])


if __name__=='__main__':unittest.main()
