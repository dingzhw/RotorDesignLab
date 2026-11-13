"""Offline release check in the selected Python environment.

Run with an explicit ROTOR_DESIGN_JULIA when Julia is not on PATH.
Python socket connections are rejected; Julia package operations are offline.
This does not change the operating system's network settings.
"""

import hashlib
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rotordesignlab.cases import THREE_BLADE, UH60, read_case, run_case


def denied(*args, **kwargs):
    raise RuntimeError("Network access rejected during offline release check")


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    os.environ["JULIA_PKG_OFFLINE"] = "true"
    checks = {}
    for name, source in (("hover", THREE_BLADE), ("uh60", UH60)):
        result = run_case(read_case(source), source.parent, output / name)
        assert result["status"] == "converged", result
        checks[name] = result["summary"]
    copied = read_case(output / "hover" / "case.json")
    replay = run_case(copied, output / "hover", output / "replay")
    assert replay["status"] == "converged", replay
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    checks["replay_csv_sha256"] = digest(output / "replay" / "radial_loads.csv")
    assert checks["replay_csv_sha256"] == digest(output / "hover" / "radial_loads.csv")
    failed = run_case(dict(copied, rpm=-1), output / "hover", output / "failed")
    assert failed["status"] == "failed" and "error" in failed
    checks["invalid_then_replay"] = "passed"
    checks["network_policy"] = "Python socket connections rejected; JULIA_PKG_OFFLINE=true"
    checks["python"] = sys.version
    (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
