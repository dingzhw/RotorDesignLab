from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from rotordesignlab.cases import read_case,read_rotor,run_case
from rotordesignlab.rotor import solve
from tools.prepare_caradonna import FREE
from tools.validate_caradonna import observables,pressure_check


SOURCE=Path(__file__).resolve().parents[1]/'validation/caradonna-tung'


class CaradonnaTest(unittest.TestCase):
    def test_observable_normalization_and_measured_airfoil_nodes(self):
        rotor,_=read_rotor(read_case(SOURCE/'hover.json'),SOURCE)
        alpha,cl,cd=np.array(FREE).T
        actual=rotor.airfoil_grid.coefficients(.8,alpha,.15,strict=True)
        np.testing.assert_allclose(actual,[cl,cd],rtol=0,atol=1e-14)
        answer=solve(rotor);summary=answer[0];data=observables(rotor,answer)
        sigma=rotor.blades*.1905/(pi*rotor.radius)
        integral=sigma/2*np.sum(data['rotor_normal_coefficient']*data['r_over_R']**2*data['dr_m']/rotor.radius)
        self.assertAlmostEqual(integral,summary['thrust_coefficient'],places=13)
        self.assertLess(summary['max_element_residual_n'],1e-6)
        self.assertAlmostEqual(summary['power_w'],summary['torque_nm']*1250*pi/30,places=8)
        self.assertLess(abs(pressure_check(SOURCE)['difference_pct']),1)

    def test_public_case_export_replay_and_reject_unsupported_mach(self):
        case=read_case(SOURCE/'hover.json')
        with TemporaryDirectory() as temporary:
            out=Path(temporary)
            first=run_case(case,SOURCE,out/'first')
            self.assertEqual(first['status'],'converged',first)
            replay=run_case(read_case(out/'first/case.json'),out/'first',out/'replay')
            self.assertEqual(first['summary'],replay['summary'])
            unsupported=run_case(dict(case,rpm=1750),SOURCE,out/'unsupported')
            self.assertEqual(unsupported['status'],'failed')
            self.assertIn('domain',unsupported['error'])


if __name__=='__main__':unittest.main()
