"""Lossless public legacy airfoil import; provenance is not upgraded to measured data."""
from pathlib import Path
import argparse,hashlib
import numpy as np
from scipy.io import loadmat
from rotordesignlab.cases import write_json

ROOT=Path(__file__).resolve().parents[1]


def build(out):
    out.mkdir(parents=True,exist_ok=True)
    raw=loadmat(ROOT/'data/GHRotorData.mat');section=dict(r_over_R=0)
    for key,stem,offset in [('cl','CLR0',0),('cd','CDR0',.002)]:
        section[key]=dict(alpha_deg=list(range(-32,33,2)),mach=np.linspace(0,1,11).tolist(),
            values=(raw[stem+'BT'].reshape(33,11,order='F')+offset).tolist(),
            outer_alpha=dict(alpha_deg=list(range(-180,181,2)),values=(raw[stem+'UT'].ravel()+offset).tolist()))
    write_json(out/'gh-full.json',dict(schema_version=1,kind='spanwise_airfoil',span_boundary='hold_endpoint',sections=[section],
        provenance='J-GenHel GHRotorData.mat: exact BT lookup for |alpha|<=32 deg, UT branch outside; CD+0.002. Original discontinuity retained; no skew correction, no new measured data.'))
    raw=loadmat(ROOT/'data/naca0012.mat');angles=raw['ALTAB'].ravel().astype(float);alpha=np.where(angles>180,angles-360,angles)
    order=np.argsort(alpha);alpha=alpha[order];unique=np.r_[True,np.diff(alpha)>0];order=order[unique];alpha=alpha[unique]
    # Source has +180 but no -180; periodic endpoint copied without changing interior values.
    slices=[]
    for i,re in enumerate(raw['RETAB'].ravel()):
        s=dict(reynolds=int(re),provenance='Legacy compiled NACA0012 MAT; original experimental provenance/Mach/transition unavailable. Mach held; not measured Mach slices.')
        for key,source in [('cl','CLTAB'),('cd','CDTAB')]:
            v=raw[source][order,i];aa=alpha
            if aa[0]>-180:aa=np.r_[-180,aa];v=np.r_[v[-1],v]
            s[key]=dict(alpha_deg=aa.tolist(),mach=[0,.85],values=np.repeat(v[:,None],2,axis=1).tolist())
        slices.append(s)
    write_json(out/'naca0012-re.json',dict(schema_version=2,kind='spanwise_airfoil',span_boundary='hold_endpoint',
        provenance='Six public legacy Reynolds slices; log(Re) interpolation, Mach held as engineering assumption, no PG scaling.',
        sections=[dict(r_over_R=0,reynolds_slices=slices)]))
    write_json(out/'source-hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'data/GHRotorData.mat',ROOT/'data/naca0012.mat']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'validation/aero-upgrade');build(p.parse_args().out)
