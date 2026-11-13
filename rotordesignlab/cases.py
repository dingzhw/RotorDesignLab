"""Versioned case inputs and replayable run directories."""

import csv
import json
from math import isclose, isfinite, pi
from pathlib import Path
import shutil
from subprocess import TimeoutExpired
import sys

import numpy as np
import scipy

from . import __version__
from .rotor import Rotor, solve
from .uh60 import ROOT, run_reference

EXAMPLES = ROOT / "examples"
UH60 = EXAMPLES / "uh60-80kt.json"
THREE_BLADE = EXAMPLES / "three-blade.json"


def read_case(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def numeric(case, key, low, high, integer=False):
    value = case.get(key)
    valid = type(value) is int if integer else type(value) in (int, float)
    if not valid or not low <= value <= high:
        raise ValueError(f"{key} 必须为 {low} 至 {high} 之间的{'整数' if integer else '数值'}。")
    return value


def table(path, columns):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if next(reader, []) != list(columns):
            raise ValueError(f"{path.name} 列名应为 {', '.join(columns)}。")
        data = np.asarray([[float(value) for value in row] for row in reader], dtype=float)
    if data.ndim != 2 or data.shape[1] != len(columns) or len(data) < 2:
        raise ValueError(f"{path.name} 至少需要两行，且每行列数一致。")
    if not np.isfinite(data).all() or not (np.diff(data[:, 0]) > 0).all():
        raise ValueError(f"{path.name} 必须为有限数值，且首列严格递增。")
    return data


def read_rotor(case, base):
    try:
        geo_path = base / case["geometry_csv"]
        polar_path = base / case["polar_csv"]
    except (KeyError, TypeError) as error:
        raise ValueError("请提供 geometry_csv 和 polar_csv 两个文件路径。") from error
    geometry = table(geo_path, ("r_over_R", "chord_m", "twist_deg"))
    polar = table(polar_path, ("alpha_deg", "cl", "cd"))
    if not (0 < geometry[0, 0] < 1 and geometry[-1, 0] == 1 and (geometry[:, 1] > 0).all()):
        raise ValueError("几何表需从正的根部半径比到 1.0，且各站弦长为正。")
    if polar[0, 0] >= 0 or polar[-1, 0] <= 0 or (polar[:, 2] < 0).any():
        raise ValueError("翼型表需覆盖正负攻角，且阻力系数非负。")
    blades = numeric(case, "blade_count", 2, 12, integer=True)
    radius = numeric(case, "radius_m", 0.03, 30)
    rpm = numeric(case, "rpm", 1, 30000)
    omega = rpm * pi / 30
    speed = numeric(case, "axial_speed_m_s", 0, 150)
    density = numeric(case, "density_kg_m3", 0.05, 3)
    collective = numeric(case, "collective_deg", -20, 55)
    reference = numeric(case, "pitch_reference_r_over_R", float(geometry[0, 0]), 1)
    stations = numeric(case, "radial_stations", 8, 2000, integer=True)
    if np.hypot(omega * radius, speed) > 250:
        raise ValueError("叶尖合速度超过当前低速翼型模型的 250 m/s 上限。")
    return Rotor(geometry, polar, blades, radius, omega, speed, density, collective, reference,
                 stations), (geo_path, polar_path)


def run_case(case, base, output):
    """Run once in a fresh directory. Save failures and normalized input files."""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("输出目录已有文件，请指定新的空目录。")
    # Exclusive creation prevents two simultaneous calls sharing an output.
    with (output / "run.lock").open("x"):
        pass
    result = dict(schema_version=1, solver_version=__version__,
                  python_version=sys.version.split()[0], numpy_version=np.__version__,
                  scipy_version=scipy.__version__, status="failed", warnings=[])
    snapshot = case.copy() if isinstance(case, dict) else case
    try:
        if not isinstance(case, dict) or type(case.get("schema_version")) is not int or case["schema_version"] != 1:
            raise ValueError("工况 JSON 必须是 schema_version 为 1 的对象。")
        result["model"] = case.get("model")
        if case.get("model") == "uh60":
            duration = numeric(case, "duration_s", 0.1, 3)
            step = numeric(case, "time_step_s", 0.0025, 0.02)
            if not isclose(duration / step, round(duration / step), rel_tol=1e-10):
                raise ValueError("仿真时长须为积分步长的整数倍。")
            run_reference(output, duration, step)
            with (output / "trim_residual.csv").open(encoding="utf-8", newline="") as stream:
                residual = max(float(row["scaled_abs"]) for row in csv.DictReader(stream))
            result.update(summary={"weighted_trim_residual": residual}, backend="Julia 1.12.4")
            result["warnings"] = ["频响采用局部线化，开环时程采用完整非线性方程。"]
        elif case.get("model") == "axial_rotor":
            rotor, sources = read_rotor(case, base)
            for key, source, name in zip(("geometry_csv", "polar_csv"), sources,
                                         ("geometry.csv", "polar.csv")):
                shutil.copyfile(source, output / name)
                snapshot[key] = name
            summary, headers, radial = solve(rotor)
            if not all(isfinite(value) for value in summary.values()):
                raise ValueError("计算产生非有限值。")
            write_csv(output / "radial_loads.csv", headers, radial)
            result.update(summary=summary, backend="Python / Pitt–Peters axial steady limit")
            result["warnings"] = ["固定桨叶、均匀轴向入流，翼型系数仅随攻角变化。"]
        else:
            raise ValueError("model 必须为 uh60 或 axial_rotor。")
        result["status"] = "converged"
    except (ValueError, RuntimeError, OSError, TimeoutExpired) as error:
        result["error"] = str(error)
    try:
        try:
            write_json(output / "case.json", snapshot)
        except (TypeError, ValueError):
            result["status"] = "failed"
            result["error"] = "工况包含不可保存的非有限数值。"
        write_json(output / "result.json", result)
    finally:
        (output / "run.lock").unlink()
    return result
