"""Run the cross-solver comparisons and report reproducible numerical checks."""

import csv
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

from rotordesignlab.cases import THREE_BLADE, read_case, read_rotor, write_csv
from rotordesignlab.legacy_check import compare_trace
from rotordesignlab.rotor import solve
from rotordesignlab.uh60 import run_julia, run_reference


def rotor_checks(directory):
    rotor, _ = read_rotor(read_case(THREE_BLADE), THREE_BLADE.parent)
    for speed in (0.0, 25.0):
        model = replace(rotor, axial_speed=speed)
        coarse, current, fine = (solve(replace(model, stations=n))[0] for n in (120, 240, 480))
        changes = {
            key: abs(current[key] / fine[key] - 1)
            for key in ("thrust_n", "torque_nm", "power_w")
        }
        assert max(changes.values()) <= 0.002, changes
        radius, widths, chord, pitch = model.grid()
        grid = directory / "grid.csv"
        write_csv(grid, ("radius", "chord", "pitch_rad", "width"), zip(radius, chord, pitch, widths))
        output = directory / f"ccblade-{speed:g}.csv"
        run_julia("ccblade_compare.jl", (grid, THREE_BLADE.parent / "synthetic-polar.csv",
                   model.radius * model.geometry[0, 0], model.radius, model.blades, speed,
                   model.omega, model.density, current["thrust_n"], output),
                  directory / f"ccblade-{speed:g}.log")
        with output.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        matched = abs(float(rows[1]["thrust_n"]) / current["thrust_n"] - 1)
        assert matched <= 0.001, matched
        print(json.dumps(dict(axial_speed=speed, thrust_120=coarse["thrust_n"],
                              python=current, radial_relative_change=changes,
                              ccblade=rows, same_thrust_relative_error=matched)))


def reference_checks(directory):
    labels = (("legacy", 0.01), ("corrected", 0.01), ("refined", 0.005), ("fine", 0.0025))
    for label, step in labels:
        target = directory / label
        target.mkdir(exist_ok=True)
        final = target / ("rotor_trace.csv" if label == "legacy" else "open_loop.csv")
        if not final.is_file() or (label == "legacy" and
                                  "flap_rate" not in final.read_text().splitlines()[0]):
            run_reference(target, step=step, legacy=label == "legacy")

    def read(label, name):
        return np.genfromtxt(directory / label / (name + ".csv"), delimiter=",", names=True)

    legacy_residual = max(read("legacy", "trim_residual")["scaled_abs"])
    np.testing.assert_allclose(legacy_residual, 0.0004968302673660219, rtol=0, atol=1e-9)
    np.testing.assert_allclose(read("legacy", "trim_controls")["value_pct"],
                               [49.7189753755, 35.1178110930, 33.9015417384, 50.8693983489],
                               rtol=0, atol=1e-7)
    old = read("legacy", "fixed_azimuth_M")
    new = read("corrected", "fixed_azimuth_M")
    acceleration_change = np.linalg.norm(old["w_ft_s"] - new["w_ft_s"])
    assert acceleration_change > 0
    assert max(read("corrected", "trim_residual")["scaled_abs"]) <= 5e-4
    errors = []
    for coarse, fine in (("corrected", "refined"), ("refined", "fine")):
        lhs, rhs = read(coarse, "open_loop"), read(fine, "open_loop")[::2]
        np.testing.assert_allclose(lhs["time_s"], rhs["time_s"], atol=1e-12)
        fields = ("p_rad_s", "q_rad_s", "r_rad_s", "roll_rad", "pitch_rad", "heading_rad")
        errors.append(max(float(np.max(np.abs(lhs[field] - rhs[field]))) for field in fields))
    assert errors[1] < errors[0] and errors[1] < 1e-4, errors
    trace = compare_trace(directory / "legacy" / "rotor_trace.csv")
    print(json.dumps(dict(legacy_residual=legacy_residual,
                          vertical_mass_matrix_column_change=float(acceleration_change),
                          time_step_max_rate_attitude_errors=errors, cross_language_trace=trace)))


if __name__ == "__main__":
    command, path = sys.argv[1:]
    directory = Path(path).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    {"rotor": rotor_checks, "reference": reference_checks}[command](directory)
