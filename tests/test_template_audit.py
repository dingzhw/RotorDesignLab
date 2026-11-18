import json
from pathlib import Path
import unittest
from rotordesignlab.template_audit import audit, source_for, NOTES
from rotordesignlab import designs, module_workspace


class TemplateAuditTests(unittest.TestCase):
    def test_catalog_coverage_and_frozen_inputs(self):
        result = audit()
        self.assertEqual(set(NOTES),set(designs.TEMPLATES)|set(module_workspace.TEMPLATES))
        saved = json.loads(Path('validation/template-audit/audit.json').read_text(encoding='utf-8'))
        self.assertEqual(result, saved)
        self.assertTrue(all(t['input_sha256'] and t['parameter_count'] for t in result['templates']))

    def test_estimates_are_not_promoted_to_measured_aircraft(self):
        name = 'UH-60 公开部件模型（含工程估计）'
        self.assertIn('工程估计',source_for(name,'/powerplant/continuous_power_w')[0])
        self.assertIn('工程假设',source_for(name,'/rotors/1/flight/flapping/first_mass_moment_kg_m')[0])
        self.assertIn('公开',source_for(name,'/rotors/0/radius_m')[0])
        self.assertIn('工程',source_for('千机-200轻型无人直升机','/mass_properties/mass_kg')[0])
