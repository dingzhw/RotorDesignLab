from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from rotordesignlab.cases import read_case,run_case,read_rotor,THREE_BLADE,write_json
from rotordesignlab.aircraft import read_aircraft,require_analysis
from rotordesignlab.azimuth import AzimuthRotor
from rotordesignlab.dynamics import rigid_body_rhs,APPARENT_MASS,frequency_response,modes,ResponseDomainError,step_response
from rotordesignlab.steady_rotor import pitt_peters,SteadyRotor

ROOT=Path(__file__).resolve().parents[1]


class DynamicsTest(unittest.TestCase):
    def test_rigid_body_mass_coupling_and_gravity_direction(self):
        mass=10.;inertia=np.array([[3.,0,-.4],[0,4.,0],[-.4,0,5.]])
        v=np.array([3.,4.,2.]);w=np.array([.1,-.2,.3]);force=np.array([7.,-3,5]);moment=np.array([1.,2.,3.])
        d=rigid_body_rhs(v,w,[0,0,0],force,moment,mass,inertia)
        np.testing.assert_allclose(mass*(d[:3]+np.cross(w,v)),force)
        np.testing.assert_allclose(inertia@d[3:6]+np.cross(w,inertia@w),moment)
        np.testing.assert_allclose(d[6:],w)
        falling=rigid_body_rhs([0,0,0],[0,0,0],[0,0,0],[0,0,98.0665],[0,0,0],mass,inertia)
        self.assertAlmostEqual(falling[2],9.80665)

    def test_dynamic_pp_reference_and_equilibrium(self):
        ref=np.loadtxt(ROOT/'validation/open-loop/julia-inflow-dynamics.csv',delimiter=',',skiprows=1)
        for row in ref:
            rate,_=pitt_peters(row[6:9],row[:3],row[3],row[4:6],dynamic=True,omega=row[9])
            np.testing.assert_allclose(rate,row[10:],atol=1e-9,rtol=1e-9)
        rate,_=pitt_peters([.05,0,0],[0,0,0],.005,[0,0],dynamic=True,omega=100)
        np.testing.assert_allclose(rate,0,atol=1e-10)
        self.assertTrue((APPARENT_MASS>0).all())

    def test_body_rate_element_velocity(self):
        rotor,_=read_rotor(read_case(THREE_BLADE),THREE_BLADE.parent);model=AzimuthRotor(rotor)
        args=([.2,0,0],[.05,0,0],[0,0,0],[0,0,0])
        a=model.elements(*args);b=model.elements(*args,body_rates=[.2,0,0])
        np.testing.assert_allclose(b['up']-a['up'],.2*a['position'][:,:,1],atol=1e-12)

    def test_flap_body_rate_terms_against_inertial_acceleration(self):
        # Differentiate blade point positions in inertial space; integrate a
        # uniform blade mass distribution to check hinge-rate forcing/signs.
        from scipy.spatial.transform import Rotation
        rotor,_=read_rotor(read_case(THREE_BLADE),THREE_BLADE.parent)
        hinge=.03;length=rotor.radius-hinge;mass=2.
        cfg=dict(mode='hinged',hinge_offset_m=hinge,precone_deg=0,max_flap_deg=15,
                 inertia_kg_m2=mass*length**2/3,first_mass_moment_kg_m=mass*length/2,spring_nm_rad=0,damper_nms_rad=0)
        model=SteadyRotor(rotor,cfg);state=np.array([.05,0,0,.03,.01,-.02]);w=np.array([.1,-.2,.03])
        a,da,_=model.evaluate(state,[.2,0,0],[10,0,0],body_rates=w)
        b,db,_=model.evaluate(state,[.2,0,0],[10,0,0])
        span=np.linspace(0,length,1001);dt=1e-5
        def positions(t,rates):
            psi=model.kernel.psi+rotor.omega*t;beta=state[3]+state[4]*np.cos(psi)+state[5]*np.sin(psi)
            er=np.column_stack((np.cos(psi),np.sin(psi),np.zeros(len(psi))))
            pos=(hinge+np.cos(beta)[:,None]*span)[:,:,None]*er[:,None,:]
            pos[:,:,2]=np.sin(beta)[:,None]*span
            return pos@Rotation.from_rotvec(rates*t).as_matrix().T
        def acceleration(rates):return (positions(dt,rates)-2*positions(0,rates)+positions(-dt,rates))/dt**2
        extra=acceleration(w)-acceleration(np.zeros(3));normal=da['normal']
        hinge_moment=np.trapezoid(np.einsum('ijk,ik->ij',extra,normal)*span*mass/length,span,axis=1)
        project=lambda values:np.array([1,2,2])*np.mean(values[:,None]*model.kernel.harmonics,axis=0)
        recovered=(a[3:]-b[3:])*cfg['inertia_kg_m2']*rotor.omega**2+project(da['flap_moment']-db['flap_moment'])
        np.testing.assert_allclose(recovered,project(hinge_moment),rtol=2e-5,atol=2e-5)

    def test_analytic_modes_and_frequency(self):
        a=np.diag(-np.arange(1,16,dtype=float));b=np.zeros((15,4));b[0,0]=2
        row=frequency_response(a,b,[1.])[0]
        self.assertAlmostEqual(row[3],np.sqrt(2));self.assertAlmostEqual(row[5],-45)
        modal=modes(a);self.assertEqual(modal[0]['real'],-1);self.assertEqual(modal[0]['participation']['u'],1)
        a[0,0]=0;a[8,8]=0;modal=modes(a)
        self.assertEqual(sum(m['behavior']=='kinematic_neutral' for m in modal),1)
        self.assertEqual(sum(m['behavior']=='near_neutral' for m in modal),1)

    def test_missing_inertia_and_failed_trim(self):
        old=read_aircraft(ROOT/'examples/trim/synthetic.json')
        old['mass_properties'].pop('inertia_cg_kg_m2',None)
        with self.assertRaisesRegex(ValueError,'惯量'):require_analysis(old,'linearize')
        with TemporaryDirectory() as tmp:
            base=ROOT/'examples/public-helicopter';c=read_case(base/'uh60-public-case.json')
            r=run_case(dict(c,analysis='linearize',speed_m_s=40),base,Path(tmp)/'failure')
            self.assertEqual(r['status'],'failed');self.assertEqual(r['solver_status'],'trim_failed')
            self.assertEqual(r['trim']['solver_status'],'converged')

    def test_response_rejects_and_retains_valid_partial_states(self):
        class Limited:
            state=np.zeros(15);controls=np.zeros(4)
            def rhs(self,x,u):
                if x[0]>.025:raise ValueError('test domain limit')
                d=np.zeros(15);d[0]=1;return d
        with self.assertRaises(ResponseDomainError) as error:
            step_response(Limited(),np.zeros((15,15)),np.zeros((15,4)),0,.1,.1,.01)
        self.assertTrue(np.all(error.exception.history[:,1]<=.025))
        self.assertGreater(len(error.exception.history),1)
        with TemporaryDirectory() as tmp:
            c=read_case(ROOT/'examples/open-loop/uh60-response.json');c['time_step_s']=.03
            r=run_case(c,ROOT/'examples/open-loop',Path(tmp)/'invalid')
            self.assertEqual(r['status'],'failed');self.assertIn('整数倍',r['error'])

    def test_linearize_replay_and_descriptor_matrices(self):
        with TemporaryDirectory() as tmp:
            base=ROOT/'examples/public-helicopter';case=read_case(base/'synthetic-case.json')
            case.update(analysis='linearize',speed_m_s=20);out=Path(tmp)/'first'
            r=run_case(case,base,out);self.assertEqual(r['status'],'converged',r)
            def load(name,n):return np.loadtxt(out/f'{name}.csv',delimiter=',',skiprows=1,usecols=range(1,n+1))
            a,b,e,f,g=load('A',15),load('B',4),load('E',15),load('F',15),load('G',4)
            np.testing.assert_allclose(np.linalg.solve(e,f),a,atol=1e-10);np.testing.assert_allclose(np.linalg.solve(e,g),b,atol=1e-10)
            self.assertEqual(r['summary']['neutral_modes'],1)
            replay=run_case(read_case(out/'case.json'),out,Path(tmp)/'replay')
            self.assertEqual(r['linearization'],replay['linearization'])
