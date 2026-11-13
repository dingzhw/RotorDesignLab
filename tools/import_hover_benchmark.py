"""Reuse audited public inputs and results from the user's Hover_BENCHMARK.

Only the explicit public-data allowlist is read/copied. No ATB or private inputs.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from rotordesignlab.airfoils import AirfoilGrid
from rotordesignlab.cases import write_json


def import_benchmark(base, output):
    inputs = base/'XV15_VALIDATION/inputs'
    manifest = json.loads((base/'reference_data_manifest.json').read_text(encoding='utf-8'))
    records = []
    def record(path, role):
        records.append(dict(file=path.relative_to(base).as_posix(), role=role,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    for source_name, target_name in [('XV15_2026_exp_data.csv','legacy_reference_ct_cq.csv'),
                                     ('XV15_2026_fom_data.csv','legacy_reference_ct_fm.csv')]:
        path = base/'sources'/source_name
        source = next(item for item in manifest if item['file'] == source_name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
        shutil.copyfile(path, output/target_name)
        record(path, 'public third-party digitization')
        records[-1]['url'] = source['url']
    # Reuse the already audited geometry; compare the independent reconstruction first.
    geometry = np.loadtxt(inputs/'geometry.csv', delimiter=',', skiprows=1)
    current = np.loadtxt(output/'geometry.csv', delimiter=',', skiprows=1)
    errors = [np.max(np.abs(np.interp(current[:,0], geometry[:,3], geometry[:,column])-current[:,newcolumn]))
              for column,newcolumn in [(1,1),(2,2)]]
    assert max(errors) < 1e-9
    np.savetxt(output/'geometry.csv', geometry[:,[3,1,2]], delimiter=',',
               header='r_over_R,chord_m,twist_deg', comments='', fmt='%.12g')
    record(inputs/'geometry.csv', 'reused public geometry, columns adapted to product format')
    # Preserve native per-coefficient Mach grids in product input, verify against all legacy nodes.
    database = AirfoilGrid.read(output/'airfoils.json')
    alpha = np.loadtxt(inputs/'alpha_deg.csv', delimiter=',')
    mach = np.loadtxt(inputs/'mach.csv', delimiter=',')
    max_error = 0.
    for index, span in enumerate(database.span, 1):
        values = database.coefficients(span, alpha[:,None], mach[None,:])
        for key, value in zip(('cl','cd'), values):
            path = inputs/f'{key}_{index}.csv'
            reference = np.loadtxt(path, delimiter=',')
            max_error = max(max_error, float(np.max(np.abs(value-reference))))
            record(path, 'legacy union-Mach-grid interpolation cross-check')
    assert max_error < 1e-10
    archived = []
    for method in ('bem','ccblade'):
        path = base/'XV15_VALIDATION'/method/'summary.csv'
        with path.open(encoding='utf-8', newline='') as stream:
            for row in csv.DictReader(stream):
                if row['case'] in ('low','mid','high'):
                    archived.append(dict(method=method,case=row['case'],ct=float(row['CT']),cq=float(row['CQ']),
                        fm=float(row['FM']),collective_deg=float(row['pitch75_deg']),axial_speed_m_s=.1,
                        status='archived model result; not rerun in this project'))
        record(path, 'archived public benchmark model result')
    with (output/'legacy_model_checks.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(archived[0]));writer.writeheader();writer.writerows(archived)
    write_json(output/'reuse-audit.json', dict(origin='User-authorized Hover_BENCHMARK public XV15 validation package',
        records=records, geometry_max_abs_difference=errors, polar_max_abs_difference=max_error,
        note='Existing geometry, reference CSVs and archived model results reused. Native NASA polar grids independently verified; no DUST rerun.'))
    print(json.dumps(dict(files=len(records),geometry_difference=errors,polar_difference=max_error)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('benchmark',type=Path)
    parser.add_argument('--out',type=Path,default=Path('validation/xv15'))
    args=parser.parse_args();import_benchmark(args.benchmark,args.out)
