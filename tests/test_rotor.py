import csv
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from rotordesignlab.cases import THREE_BLADE, read_case, read_rotor, run_case
from rotordesignlab.rotor import solve


class RotorTest(unittest.TestCase):
    def setUp(self):
        self.case = read_case(THREE_BLADE)
        self.rotor, _ = read_rotor(self.case, THREE_BLADE.parent)

    def test_hover_and_axial_integral_closure(self):
        for speed in (0.0, 25.0):
            rotor = replace(self.rotor, axial_speed=speed)
            values, names, rows = solve(rotor)
            data = np.asarray(list(rows))
            self.assertGreater(values["thrust_n"], 0)
            self.assertLess(abs(values["residual_n"]), 1e-6)
            self.assertAlmostEqual(data[:, names.index("dthrust_n")].sum(), values["thrust_n"], places=8)
            self.assertAlmostEqual(data[:, names.index("dtorque_nm")].sum(), values["torque_nm"], places=8)
            self.assertAlmostEqual(values["power_w"], rotor.omega * values["torque_nm"], places=8)
            self.assertAlmostEqual(values["moment_x_nm"], 0, places=8)
            self.assertAlmostEqual(values["moment_y_nm"], 0, places=8)

    def test_radial_refinement(self):
        keys = ("thrust_n", "torque_nm", "power_w")
        for speed in (0.0, 25.0):
            levels = [solve(replace(self.rotor, axial_speed=speed, stations=n))[0] for n in (120, 240, 480)]
            for key in keys:
                with self.subTest(speed=speed, key=key):
                    self.assertLess(abs(levels[1][key] / levels[2][key] - 1), 0.002)

    def test_replay_and_failed_result(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            first = run_case(self.case, THREE_BLADE.parent, base / "first")
            self.assertEqual(first["status"], "converged")
            case = read_case(base / "first" / "case.json")
            replay = run_case(case, base / "first", base / "replay")
            self.assertEqual(first["summary"], replay["summary"])
            failed = run_case(dict(case, rpm=-1), base / "first", base / "failed")
            self.assertEqual(failed["status"], "failed")
            self.assertTrue((base / "failed" / "result.json").is_file())
            self.assertFalse((base / "failed" / "radial_loads.csv").exists())
            with self.assertRaisesRegex(ValueError, "输出目录"):
                run_case(case, base / "first", base / "replay")
            with (base / "replay" / "radial_loads.csv").open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), self.rotor.stations)
