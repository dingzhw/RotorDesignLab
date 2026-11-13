"""Run the headless, pinned J-GenHel reference model."""

import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]


def julia_executable():
    executable = os.environ.get("ROTOR_DESIGN_JULIA") or shutil.which("julia")
    if not executable:
        raise RuntimeError("找不到 Julia 1.12.4，请设置 ROTOR_DESIGN_JULIA。")
    return executable


def run_julia(script, arguments, log):
    with log.open("wb") as stream:
        result = subprocess.run(
            [julia_executable(), "--startup-file=no", "--compiled-modules=existing",
             f"--project={ROOT / 'julia'}", str(ROOT / "julia" / script),
             *map(str, arguments)],
            cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=420,
            env={**os.environ, "JULIA_PKG_OFFLINE": "true"},
        )
    if result.returncode:
        details = log.read_text(encoding="utf-8", errors="replace").splitlines()
        headline = next((line for line in details if line.startswith("ERROR:")), "")
        raise RuntimeError(f"Julia 求解失败。{headline} 日志见 {log.name}。")


def run_reference(output, duration=1.0, step=0.01, legacy=False):
    with TemporaryDirectory(dir=output) as staging:
        tables = Path(staging)
        for source in sorted((ROOT / "data").glob("*.mat")):
            table = tables / source.name
            table.mkdir()
            for name, values in loadmat(source).items():
                if not name.startswith("__"):
                    if values.ndim != 2 or not np.isfinite(values).all():
                        raise ValueError(f"Invalid MAT table {source.name}:{name}")
                    np.savetxt(table / f"{name}.csv", values, delimiter=",", fmt="%.17g")
        run_julia("uh60.jl", (tables, output, "legacy" if legacy else "corrected",
                             duration, step), output / "solver.log")
