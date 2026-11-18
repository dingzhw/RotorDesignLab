"""Integrate explicitly piecewise-constant radial mass data; never tune inertia."""
import argparse
from copy import deepcopy
from pathlib import Path
import numpy as np
from rotordesignlab import designs
from rotordesignlab.cases import write_json
from tools.audit_a3_mass import audit
from tools.verify_a3_aircraft import candidate


def integrate_segments(edges_m, density_kg_m, hinge_m):
    edges = np.asarray(edges_m, dtype=float)
    density = np.asarray(density_kg_m, dtype=float)
    if (edges.ndim != 1 or density.shape != (len(edges)-1,) or
            not np.isfinite(edges).all() or not np.isfinite(density).all() or
            not np.isfinite(hinge_m) or np.any(np.diff(edges) <= 0) or np.any(density < 0)):
        raise ValueError('质量分段需严格递增边界、有限非负线密度及有限铰位置。')
    # Moments measured OUTBOARD of the flap hinge; SI kg, kg m, kg m².
    left = np.maximum(edges[:-1], hinge_m)-hinge_m
    right = np.maximum(edges[1:], hinge_m)-hinge_m
    return [float(np.sum(density*(right**(k+1)-left**(k+1))/(k+1))) for k in range(3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    root = Path(__file__).resolve().parents[1]
    table = np.loadtxt(root/'validation/hub-loads/uh60-cr166155-mass.csv', delimiter=',', skiprows=1)
    edges = np.r_[0., np.cumsum(table[:, 0])*.01]
    integrated = integrate_segments(edges, table[:, 1], .381)
    # Table 13/22 uses force-based units for the first moment: lb s² × N/lbf.
    source = [118.82, 86.838*4.4482216152605, 2053.2]
    design = candidate(designs.from_template('UH-60 公开部件模型（含工程估计）'), 'uh60')
    before = deepcopy(design)
    main_rotor = next(r for r in design['aircraft']['rotors'] if r['role'] == 'main')
    for key, value in zip(('mass_kg', 'first_mass_moment_kg_m', 'inertia_kg_m2'), source):
        main_rotor['blade_mass'][key] = value
        if key != 'mass_kg':
            main_rotor['flight']['flapping'][key] = value
    write_json(args.out, dict(
        source='NASA CR-166155 Tables 13/22, printed pp76/85; PDF pp81/90',
        source_url='https://ntrs.nasa.gov/citations/19830004795',
        interpretation='Same-report main-blade moments only; not same-configuration aircraft closure',
        radius_from_rounded_segments_m=float(edges[-1]), hinge_m=.381,
        integrated_m0_m1_m2_si=integrated, printed_m0_m1_m2_si=source,
        segment_vs_summary_relative_difference=(np.array(integrated)/source-1).tolist(),
        prior_main_blade=next(r['blade_mass'] for r in before['aircraft']['rotors'] if r['role']=='main'),
        original_partition=audit(before), updated_main_only_partition=audit(design),
        remaining_gaps=['Main hub mass/tensor', 'Tail blade/hub same-configuration mass moments',
                        'Reference configuration and total inertia compatibility with TM-85890'],
        nps_status='Appendix C searchable BMASS text has repeated station 22; original image not checked; 369D/E adapted to 369C; not adopted'))


if __name__ == '__main__':
    main()
