"""RotorDesignLab command line."""

import argparse
import json
from pathlib import Path
import sys

from .cases import read_case, run_case


def main():
    parser = argparse.ArgumentParser(prog="rotordesignlab")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a versioned JSON case")
    run.add_argument("case", type=Path)
    run.add_argument("--out", type=Path, required=True)
    batch = commands.add_parser('batch', help='Run an aircraft rotor performance sweep')
    batch.add_argument('case', type=Path)
    batch.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'batch':
            from .batch import run_batch
            result = run_batch(read_case(args.case), args.case.resolve().parent, args.out)
        else:
            result = run_case(read_case(args.case), args.case.resolve().parent, args.out)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "converged" else 2


if __name__ == "__main__":
    sys.exit(main())
