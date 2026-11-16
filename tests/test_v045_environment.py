from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
import pandas as pd
from rotordesignlab.environment import standard, from_case, AIR_FIELDS
from rotordesignlab.cases import run_case, read_case
from rotordesignlab.engineering_display import result_table
from rotordesignlab.previews import layout_figure, csv_figure, polar_figure
from rotordesignlab import designs

ROOT = Path(__file__).resolve().parents[1]


class EnvironmentTests(unittest.TestCase):
    def test_standard_levels_temperature_and_unchanged_legacy(self):
        for altitude, density in ((0, 1.225), (3000, .909122), (4500, .77678)):
            base = standard(altitude)
            self.assertAlmostEqual(base['density_kg_m3'], density, delta=2e-5)
            warm = standard(altitude, 15)
            self.assertEqual(base['pressure_pa'], warm['pressure_pa'])
            self.assertAlmostEqual(warm['density_kg_m3'] / base['density_kg_m3'], base['temperature_k'] / warm['temperature_k'])
            self.assertAlmostEqual((warm['speed_of_sound_m_s'] / base['speed_of_sound_m_s'])**2, warm['temperature_k'] / base['temperature_k'])
            self.assertGreater(warm['dynamic_viscosity_pa_s'], base['dynamic_viscosity_pa_s'])
            # Exact equations/constants of the previous hover.atmosphere.
            temperature = 288.15 - .0065 * altitude
            pressure = 101325 * (temperature / 288.15)**(9.80665 / (287.05287 * .0065))
            self.assertEqual(base['density_kg_m3'], pressure / (287.05287 * temperature))
        for case in ({'environment': {}}, {'environment': {'mode': 'custom', 'density_kg_m3': 1.2}},
                     {'environment': {'mode': 'isa', 'density_kg_m3': 1.2}}, {'altitude_m': -1},
                     {'environment': {'mode': 'isa', 'isa_temperature_offset_k': float('nan')}}):
            with self.assertRaises(ValueError):
                from_case(case)

    def test_isolated_custom_matches_legacy_and_replay(self):
        path = ROOT / 'examples/templates/v045'
        with TemporaryDirectory() as directory:
            case = dict(schema_version=2, model='spatial_rotor', aircraft_json='synthetic.json', rotor_id='main',
                        flow_body_m_s=[-10., 0., 0.], rpm=1700, collective_deg=13., radial_stations=24,
                        azimuth_stations=24, flapping_model='fixed', density_kg_m3=1.1,
                        speed_of_sound_m_s=330., dynamic_viscosity_pa_s=1.8e-5)
            legacy = run_case(case, path, Path(directory) / 'old')
            new = {key: value for key, value in case.items() if key not in AIR_FIELDS}
            new['environment'] = dict(mode='custom', **{key: case[key] for key in AIR_FIELDS})
            result = run_case(new, path, Path(directory) / 'new')
            self.assertEqual(result['status'], 'converged', result)
            self.assertEqual(result['summary'], legacy['summary'])
            saved = Path(directory) / 'new/case.json'
            replay = run_case(read_case(saved), saved.parent, Path(directory) / 'replay')
            self.assertEqual(replay['summary'], result['summary'])
            invalid = dict(new, density_kg_m3=1.1)
            rejected = run_case(invalid, path, Path(directory) / 'rejected')
            self.assertEqual(rejected['status'], 'failed')
            self.assertIn('不可同时', rejected['error'])

    def test_common_environment_budget_trim_and_linearize(self):
        base = ROOT / 'examples/templates/v045'
        with TemporaryDirectory() as directory:
            for analysis in ('hover_budget', 'trim', 'linearize'):
                case = dict(schema_version=3, model='helicopter', analysis=analysis, aircraft_json='synthetic.json',
                            altitude_m=1000., requested_duration_s=60., radial_stations=24,
                            environment=dict(mode='isa', isa_temperature_offset_k=15.))
                if analysis != 'hover_budget':
                    case.update(speed_m_s=10., climb_m_s=0., azimuth_stations=24)
                if analysis == 'linearize':
                    case['frequencies_rad_s'] = [.1, 1.]
                air = from_case(case)
                a = run_case(case, base, Path(directory) / (analysis + '-isa'))
                custom = dict(case, environment=dict(mode='custom', **{k: air[k] for k in AIR_FIELDS}))
                b = run_case(custom, base, Path(directory) / (analysis + '-custom'))
                self.assertEqual(a['status'], 'converged', a)
                self.assertEqual(b['status'], 'converged', b)
                self.assertEqual(a.get('summary'), b.get('summary'))
                if analysis == 'linearize':
                    for filename in ('A.csv', 'B.csv'):
                        self.assertEqual((Path(directory) / (analysis + '-isa') / filename).read_bytes(),
                                         (Path(directory) / (analysis + '-custom') / filename).read_bytes())

    def test_chinese_kw_display_does_not_change_si_data(self):
        frame = pd.DataFrame(dict(quantity=['power_w', 'thrust_n'], value=[1234, 100]))
        display = result_table(frame)
        self.assertEqual(display['数值'][0], 1.234)
        self.assertEqual(display['物理量'][0], '轴功率 / kW')
        self.assertEqual(frame['value'][0], 1234)
        wide = result_table(pd.DataFrame(dict(main_power_w=[12340], status=['converged'])))
        self.assertEqual(wide.iloc[0, 0], 12.34)
        self.assertEqual(wide.iloc[0, 1], '收敛')

    def test_density_sweep_custom_environment_and_isa_rejection(self):
        from rotordesignlab.batch import run_batch
        base = ROOT / 'examples/templates/v045'
        case = dict(schema_version=2, model='aircraft_rotor', aircraft_json='synthetic.json', rotor_id='main',
                    rpm=1700, collective_deg=13, radial_stations=24, axial_speed_m_s=0.,
                    environment=dict(mode='custom', density_kg_m3=1.2, speed_of_sound_m_s=340.3, dynamic_viscosity_pa_s=1.7894e-5))
        with TemporaryDirectory() as directory:
            from rotordesignlab.cases import write_json
            source = Path(directory) / 'case.json'
            case['aircraft_json'] = str(base / 'synthetic.json')
            write_json(source, case)
            spec = dict(schema_version=1, kind='rotor_sweep', case_json=str(source), axes={'density_kg_m3': [1.1, 1.2]})
            result = run_batch(spec, base, Path(directory) / 'custom')
            self.assertEqual(result['status'], 'converged', result)
            snap = read_case(Path(directory) / 'custom/case-0000/case.json')
            self.assertEqual(snap['environment']['density_kg_m3'], 1.1)
            case['environment'] = {'mode': 'isa'}
            write_json(source, case)
            rejected = run_batch(spec, base, Path(directory) / 'isa')
            self.assertEqual(rejected['status'], 'failed')
            self.assertIn('密度扫描', rejected['error'])
            case['environment'] = 'invalid'
            write_json(source, case)
            malformed = run_batch(spec, base, Path(directory) / 'malformed')
            self.assertEqual(malformed['status'], 'failed')

    def test_previews_use_current_geometry_and_raw_polar(self):
        from matplotlib import pyplot as plt
        design = designs.from_template(next(iter(designs.TEMPLATES)))
        rotor = design['aircraft']['rotors'][0]
        fig = layout_figure(design['aircraft'])
        self.assertEqual(len(fig.axes), 2)
        plt.close(fig)
        fig = csv_figure(design['assets'][rotor['geometry_csv']], True)
        data = np.loadtxt(design['assets'][rotor['geometry_csv']].splitlines(), delimiter=',', skiprows=1)
        np.testing.assert_array_equal(fig.axes[0].lines[0].get_ydata(), data[:, 1])
        plt.close(fig)
        fig = polar_figure(dict(alpha_deg=[-10, 0, 10], mach=[0, .2], values=[[-1, -1.1], [0, 0], [1, 1.1]]), 'cl')
        np.testing.assert_array_equal(fig.axes[0].lines[1].get_ydata(), [-1.1, 0, 1.1])
        plt.close(fig)


if __name__ == '__main__':
    unittest.main()
