"""Check the declared total-inertia interpretation without changing source files."""
import argparse
from copy import deepcopy
from pathlib import Path
import numpy as np
from rotordesignlab import designs
from rotordesignlab.cases import write_json
from rotordesignlab.mass_partition import Partition, skew, spatial_mass
from tools.verify_a3_aircraft import candidate


def audit(design):
    aircraft = design['aircraft']
    props = aircraft['mass_properties']
    temporary = deepcopy(aircraft)
    temporary['mass_properties']['inertia_cg_kg_m2'] = (np.eye(3)*1e6).tolist()
    partition = Partition(temporary)
    rotating = spatial_mass(props['mass_kg'], np.zeros(3), np.eye(3)*1e6)-partition.core_matrix
    remainder = spatial_mass(props['mass_kg'], np.zeros(3), props['inertia_cg_kg_m2'])-rotating
    mass = np.trace(remainder[:3, :3])/3
    block = remainder[3:, :3]
    cg = np.array([block[2, 1], block[0, 2], block[1, 0]])/mass
    inertia = remainder[3:, 3:]+mass*skew(cg)@skew(cg)
    principal = np.linalg.eigvalsh(inertia)
    covariance = .5*np.trace(inertia)*np.eye(3)-inertia
    return dict(total_mass_kg=props['mass_kg'], total_inertia_kg_m2=props['inertia_cg_kg_m2'],
        remaining_mass_kg=float(mass), remaining_cg_relative_m=cg.tolist(),
        remaining_inertia_kg_m2=inertia.tolist(), remaining_principal_inertia_kg_m2=principal.tolist(),
        triangle_margin_kg_m2=float(principal[:2].sum()-principal[2]),
        minimum_mass_second_moment_eigenvalue_kg_m2=float(np.linalg.eigvalsh(covariance)[0]),
        realizable=bool(principal[0]>0 and principal[:2].sum()>=principal[2]),
        interpretation='Contradiction among total interpretation and adopted rotor data; does not prove core-inertia interpretation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    original = args.package.read_bytes()
    oh6 = designs.unpack(original)
    uh60 = designs.from_template('UH-60 公开部件模型（含工程估计）')
    report = {name: audit(candidate(model, name)) for name, model in [('oh6', oh6), ('uh60', uh60)]}
    assert args.package.read_bytes() == original
    write_json(args.out, report)


if __name__ == '__main__':
    main()
