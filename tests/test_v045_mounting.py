from copy import deepcopy
from pathlib import Path
import unittest
import numpy as np
from rotordesignlab.aircraft import read_aircraft
from rotordesignlab.coordinates import selected_basis
from rotordesignlab.mounting import tilt_basis, mount_angles, advancing_direction, azimuth_figure
from rotordesignlab.trim import TrimSystem

ROOT = Path(__file__).resolve().parents[1]


class MountingTests(unittest.TestCase):
    def test_projection_angles_basis_and_legacy_roundtrip(self):
        for stem in ('synthetic', 'uh60-public'):
            for version in ('v044', 'v045'):
                aircraft = read_aircraft(ROOT / f'examples/templates/{version}/{stem}.json')
                for rotor in aircraft['rotors']:
                    angles = mount_angles(rotor)
                    b = tilt_basis(rotor['role'], **angles)
                    np.testing.assert_allclose(b, selected_basis(rotor), atol=2e-15)
                    np.testing.assert_allclose(b.T @ b, np.eye(3), atol=2e-15)
                    self.assertAlmostEqual(np.linalg.det(b), 1.)
        for role in ('main', 'tail'):
            for side in (-1, 1):
                basis = tilt_basis(role, 5, -4, 37, side)
                rotor = dict(role=role, thrust_axis_body=basis[:, 2].tolist(), flight={'x_reference_body': basis[:, 0].tolist()})
                np.testing.assert_allclose(tilt_basis(role, **mount_angles(rotor)), basis, atol=1e-14)
                self.assertGreater(basis[0, 2], 0.)
                self.assertLess(basis[1, 2], 0.) if role == 'main' else self.assertGreater(basis[2, 2], 0.)
        with self.assertRaises(ValueError):
            tilt_basis('main', 90, 0, 0)

    def test_advancing_side_matches_local_velocity_both_rotations_and_tail(self):
        aircraft = read_aircraft(ROOT / 'examples/templates/v045/synthetic.json')
        for rotor in aircraft['rotors']:
            for sign in (-1, 1):
                rotor['rotation_sign'] = sign
                flow = [-15., -2., 3.]
                direction = advancing_direction(rotor, flow)
                velocity = -selected_basis(rotor).T @ flow
                tangent = sign * np.array([-direction[1], direction[0]])
                self.assertAlmostEqual(tangent @ velocity[:2], np.linalg.norm(velocity[:2]))
                self.assertIsNone(advancing_direction(rotor, [0, 0, 0]))
        main = aircraft['rotors'][0]
        main['rotation_sign'] = 1
        body = selected_basis(main) @ np.r_[advancing_direction(main, [-15., 0, 0]), 0.]
        np.testing.assert_allclose(body, [0, 1, 0], atol=1e-14)

    def test_same_installed_loads_when_phase_rotates_half_turn(self):
        for stem in ('synthetic', 'uh60-public'):
            path = ROOT / f'examples/templates/v044/{stem}.json'
            aircraft = read_aircraft(path)
            for rotor in aircraft['rotors']:
                rotor['defaults']['radial_stations'] = 24
            case = dict(altitude_m=0, speed_m_s=15., climb_m_s=2., azimuth_stations=24)
            for sign in (-1, 1):
                aircraft['rotors'][0]['rotation_sign'] = sign
                old = TrimSystem(aircraft, path.parent, case)
                updated = deepcopy(aircraft)
                updated['rotors'][0]['flight']['x_reference_body'] = [-1, 0, 0]
                new = TrimSystem(updated, path.parent, case)
                x = old.initial()
                x[1:3] = [.01, -.02]
                x[6:12] = [.045, .002, -.001, .03, .01, -.02]
                mapped = x.copy()
                mapped[[1, 2, 7, 8, 10, 11]] *= -1
                _, a = old.evaluate(x)
                _, b = new.evaluate(mapped)
                for role in ('main', 'tail'):
                    for key in ('force_body_n', 'moment_cg_body_nm', 'power_w', 'torque_nm'):
                        np.testing.assert_allclose(b['components'][role][key], a['components'][role][key], rtol=1e-11, atol=1e-9)

    def test_figure_hover_and_pitch_definition(self):
        from matplotlib import pyplot as plt
        rotor = read_aircraft(ROOT / 'examples/templates/v045/synthetic.json')['rotors'][0]
        fig = azimuth_figure(rotor, [0, 0, 0], [13, 2, -1])
        self.assertFalse(any(text.get_text() == '前行侧' for text in fig.axes[0].texts))
        theta = fig.axes[1].lines[0].get_ydata()
        np.testing.assert_allclose(theta[[0, 45, 90, 135, 180]], [15, 12, 11, 14, 15])
        plt.close(fig)


if __name__ == '__main__':
    unittest.main()
