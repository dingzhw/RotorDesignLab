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
    extract = commands.add_parser('extract-rotor', help='从旧机型或方案包另存独立旋翼模块')
    extract.add_argument('source', type=Path)
    extract.add_argument('--rotor-id', required=True)
    extract.add_argument('--out', type=Path, required=True)
    extract.add_argument('--case', type=Path, help='可选：将同一旋翼的旧孤立工况转换到模块局部系')
    args = parser.parse_args()
    try:
        if args.command == 'extract-rotor':
            from .rotor_module import extract, convert_case
            result = extract(args.source, args.rotor_id, args.out)
            if args.case:
                from .cases import write_json
                converted = convert_case(read_case(args.case), read_case(args.out/'migration.json'), read_case(args.out/'case.json'))
                write_json(args.out/'converted-case.json', converted)
        elif args.command == 'batch':
            from .batch import run_batch
            result = run_batch(read_case(args.case), args.case.resolve().parent, args.out)
        else:
            result = run_case(read_case(args.case), args.case.resolve().parent, args.out)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True))
    restriction = result.get('evaluation_restriction', {})
    if restriction.get('issue'):
        print(restriction['note'], file=sys.stderr)
        if result['status'] == 'converged' and not result.get('diagnostic_only', False):
            return 3
    return 0 if result["status"] == "converged" else 2


if __name__ == "__main__":
    sys.exit(main())
