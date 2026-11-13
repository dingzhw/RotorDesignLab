from copy import deepcopy
from pathlib import Path
import unittest
import numpy as np
from scipy.io import loadmat
from scipy.interpolate import RegularGridInterpolator
from rotordesignlab.airfoils import AirfoilGrid

ROOT=Path(__file__).resolve().parents[1]


class AeroUpgradeTest(unittest.TestCase):
    def test_legacy_branches_against_independent_lookup(self):
        g=AirfoilGrid.read(ROOT/'validation/aero-upgrade/gh-full.json');raw=loadmat(ROOT/'data/GHRotorData.mat')
        a=np.array([-179,-90,-32.00001,-32,-3.25,31.999,32,32.00001,90,179]);m=np.linspace(.02,.9,len(a))
        got=g.coefficients(.6,a,m,strict=True)
        for result,stem,offset in zip(got,['CLR0','CDR0'],[0,.002]):
            inner=RegularGridInterpolator((np.arange(-32,33,2),np.linspace(0,1,11)),raw[stem+'BT'].reshape(33,11,order='F'))(np.c_[np.clip(a,-32,32),m])
            outer=np.interp(a,np.arange(-180,181,2),raw[stem+'UT'].ravel())
            np.testing.assert_allclose(result,np.where(abs(a)<=32,inner,outer)+offset,atol=1e-14)

    def test_log_re_nodes_domains_and_legacy(self):
        g=AirfoilGrid.read(ROOT/'validation/aero-upgrade/naca0012-re.json')
        raw=loadmat(ROOT/'data/naca0012.mat');nodes=raw['RETAB'].ravel().astype(float)
        for i,re in enumerate(nodes):
            cl,cd=g.coefficients(.5,3.,.15,reynolds=re,strict=True)
            self.assertAlmostEqual(float(cl),raw['CLTAB'][3,i]);self.assertAlmostEqual(float(cd),raw['CDTAB'][3,i])
        cl,cd=g.coefficients(.5,3.,.15,reynolds=np.sqrt(nodes[0]*nodes[1]),strict=True)
        self.assertAlmostEqual(float(cd),np.mean(raw['CDTAB'][3,:2]))
        with self.assertRaisesRegex(ValueError,'Reynolds'):g.coefficients(.5,3.,.15,reynolds=1e4,strict=True)
        with self.assertRaises(ValueError):g.coefficients(.5,3.,.15,reynolds=-1)
        with self.assertRaises(ValueError):g.coefficients(.5,3.,.15)
        old=AirfoilGrid.read(ROOT/'validation/caradonna-tung/airfoils.json')
        np.testing.assert_equal(old.coefficients(.5,3,.15),old.coefficients(.5,3,.15,reynolds=1e3))

    def test_independent_slice_grids(self):
        def table(a,m):return dict(alpha_deg=a,mach=m,values=[[x+y for y in m] for x in a])
        data=dict(schema_version=2,kind='spanwise_airfoil',span_boundary='hold_endpoint',sections=[dict(r_over_R=.5,
            reynolds_slices=[dict(reynolds=1e5,cl=table([-2,0,2],[0,.4]),cd=table([-2,0,2],[0,.4])),
                             dict(reynolds=1e6,cl=table([-3,1,3],[0,.2,.5]),cd=table([-3,1,3],[0,.2,.5]))])])
        for s in data['sections'][0]['reynolds_slices']:
            s['cd']['values']=(np.array(s['cd']['values'])+10).tolist()
        g=AirfoilGrid(data);cl,cd=g.coefficients(.5,.5,.1,reynolds=10**5.5,strict=True)
        self.assertAlmostEqual(float(cl),.6);self.assertAlmostEqual(float(cd),10.6)
