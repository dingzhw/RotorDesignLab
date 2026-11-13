"""Rebuild the public C–T benchmark from reviewed transcriptions, not fitted data."""
import argparse
import hashlib
from pathlib import Path

import numpy as np

from rotordesignlab.cases import write_csv, write_json


CT_SHA = '16c14789a5f65892b4ffb4e3628872723195c930f96680068ead7375e57208d2'
LADSON_SHA = '8e466706cbdf54b3c778ea2b089c4f52d87686bf7f6b1bd10d224b42c2d06902'
# NASA TM-4074, printed p.6 (PDF p.8), Table I, Re=2e6, M=.15.
# Only the attached-flow subset with both CL and CD reported is imported.
FREE = [(-4.25,-.4300,.00730),(-2.10,-.2150,.00620),(0,0,.00620),
        (1.85,.1940,.00620),(4.25,.4450,.00670),(6.05,.6250,.00870),
        (8.15,.8550,.01270),(10.15,1.0450,.01350),(11.15,1.1350,.01490),
        (12.10,1.2180,.01640),(13.08,1.2900,.01880),(14.25,1.3620,.02280),(15.25,1.4080,.02910)]
# Same Re/M, Table VII, printed p.16 (PDF p.18), 60-W grit fixed transition.
FIXED = [(-4.16,-.4300,.01213),(-2.14,-.2271,.01080),(-.03,-.0102,.01091),
         (0,-.0060,.01100),(1.97,.1970,.01084),(4.14,.4219,.01152),
         (5.98,.6084,.01336),(8.10,.8123,.01631),(10.04,.9789,.02093)]


def make_airfoil(raw, *, pg=True, name='free transition'):
    """PG lift scaling relative to measured M=.15; CD held at measured values.

    Negative alpha below the measured negative limit is reflected from positive
    alpha for uniform-inflow inner elements. This extension is modelled data.
    """
    extra=[(-a,-cl,cd) for a,cl,cd in raw if a > -raw[0][0]]
    data=np.array(sorted(extra+raw)); mach=np.linspace(0,.5,51)
    correction=np.sqrt(1-.15**2)/np.sqrt(1-mach**2) if pg else np.ones_like(mach)
    return dict(schema_version=1,kind='spanwise_airfoil',span_boundary='hold_endpoint',
        provenance=dict(source='NASA TM-4074',reynolds=2000000,measured_mach=.15,
            transition=name,alpha_extension='odd CL/even CD reflection below measured negative-alpha limit',
            mach_model='Prandtl-Glauert CL relative to M=.15; CD held' if pg else 'CL/CD held at M=.15',
            caution='Mach-generated nodes are model estimates, not additional wind-tunnel data.'),
        sections=[dict(r_over_R=.5,name='NACA 0012',
            cl=dict(alpha_deg=data[:,0].tolist(),mach=mach.tolist(),values=(data[:,1,None]*correction).tolist()),
            cd=dict(alpha_deg=data[:,0].tolist(),mach=mach.tolist(),values=np.repeat(data[:,2,None],len(mach),axis=1).tolist()))])


def prepare(source, out):
    for filename,expected in [('Caradonna_Tung_TM81232.pdf',CT_SHA),('NACA0012_TM4074.pdf',LADSON_SHA)]:
        actual=hashlib.sha256((source/filename).read_bytes()).hexdigest()
        if actual != expected:raise ValueError(f'Unexpected source hash: {filename}')
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'geometry.csv',['r_over_R','chord_m','twist_deg'],[(1/6,.1905,0),(1,.1905,0)])
    write_csv(out/'ladson-free.csv',['alpha_deg','cl','cd'],FREE)
    write_csv(out/'ladson-fixed.csv',['alpha_deg','cl','cd'],FIXED)
    write_json(out/'airfoils.json',make_airfoil(FREE))
    write_json(out/'hover.json',dict(schema_version=1,model='axial_rotor',blade_count=2,radius_m=1.143,
        rpm=1250,axial_speed_m_s=0,density_kg_m3=1.225,collective_deg=8,
        pitch_reference_r_over_R=.75,radial_stations=480,geometry_csv='geometry.csv',polar_json='airfoils.json',
        precone_deg=.5,speed_of_sound_m_s=1250*np.pi/30*1.143/.439,inflow_model='annular',tip_loss='prandtl'))
    # Original Table 17 bottom row, PDF p.28 / printed p.26. Figure 6 is a cross-check only.
    write_csv(out/'reference.csv',['r_over_R','cl_reported','rounding_half_unit','table','pdf_page'],
        [(r,cl,.00005,17,28) for r,cl in zip([.5,.68,.8,.89,.96],[.2345,.2815,.2886,.3143,.2683])])
    # One complete pressure section independently checks sign/integration scale.
    # Values are NEGATIVE Cp, exactly as headed in Table 17; no sign reversal at import.
    xu=[0,.01,.04,.07,.09,.13,.17,.21,.24,.30,.35,.42,.50,.56,.65,.76,.90]
    u=[.375,.9164,1.091,.8797,.8553,.7617,.7169,.6477,.5785,.4849,.4483,.3831,.318,.2651,.202,.1145,-.01576]
    xl=[.01,.02,.11,.14,.24,.34,.57,.74,.90]
    l=[-.5408,-.378,.09415,.1593,.1959,.1959,.1306,.06158,-.0239]
    write_csv(out/'pressure-r080.csv',['surface','x_over_c','minus_cp'],
        [(side,x,value) for side,xx,yy in [('upper',xu,u),('lower',xl,l)] for x,value in zip(xx,yy)])
    write_json(out/'provenance.json',dict(
        sources=[dict(id='CT',url='https://ntrs.nasa.gov/api/citations/19820004169/downloads/19820004169.pdf',
            sha256=CT_SHA,used='experiment pp.2–3; Figure 1; Table 17; Figure 6'),
            dict(id='LADSON',url='https://ntrs.nasa.gov/api/citations/19880019495/downloads/19880019495.pdf',
                 sha256=LADSON_SHA,used='Table I Re=2e6 subset; Table VII Re=2e6 sensitivity'),
            dict(id='FERLISI',url='https://publications.polymtl.ca/3059/1/208_CarloFerlisi.pdf',
                 used='Table 4.1: numerical root-cutout convention 0.1905 m; not a new experimental measurement')],
        transcription='Manual, checked against rendered original tables and independent OCR where legible.',
        reference=dict(rpm=1250,collective_deg=8,mach_tip=.439,ct=.00460,
            ct_source='Figure 6, 1250 rpm filled circles',load_source='Table 17, five sectional CL values',
            precision='0.00005 is table rounding only; experimental error bars unavailable'),
        assumptions=dict(root_cutout_r_R=1/6,root_sensitivity_r_R=[.1,.243],density_kg_m3=1.225,
            dynamic_viscosity_pa_s=1.7894e-5,airfoil_reynolds=2000000,
            transition='free; fixed-transition sensitivity is a separate run',
            pg='weak-compressibility lift estimate; not a measured Mach/Re airfoil map',
            comparison='rotor-normal force per blade/chord normalized by 0.5*rho*(Omega*r)^2',
            projection_gap='Original report does not fully specify the CL integration/projection algorithm; alternative chord-normal and relative-flow lift definitions are exported.'),
        missing=['Mach/Re-resolved NACA0012 data over the full radial domain',
                 'experimental root-cutout drawing and exact ambient state',
                 'experimental transition/roughness and load uncertainty',
                 'pressure-integration endpoint/quadrature/projection convention',
                 'nonlocal wake contraction, tip-vortex interaction, root loss and elastic blade response']))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,default=Path('runs/public-sources'))
    parser.add_argument('--out',type=Path,default=Path('validation/caradonna-tung'))
    args=parser.parse_args();prepare(args.sources,args.out)
