"""Coupled steady Pitt-Peters inflow and three-harmonic rigid-blade flapping.

Steady inflow and quasi-steady flapping, with optional hub angular rates.
Mean and harmonic mass-flow speeds are distinct to recover axial momentum.
"""
from math import pi
import numpy as np
from scipy.optimize import brentq,least_squares

from .azimuth import AzimuthRotor


def pitt_peters(inflow, velocity, thrust_coefficient, pressure_moments, *, dynamic=False, omega=1.):
    """Rotor x is upstream for positive vx. Pressure moments are [x*T,y*T]."""
    mu=float(np.linalg.norm(velocity[:2]));uz=float(velocity[2])
    wind=np.array([1.,0.]) if mu<1e-12 else np.asarray(velocity[:2])/mu
    transform=np.array([[wind[0],wind[1]],[-wind[1],wind[0]]])
    # Positive branch for the coefficients during nonlinear trial evaluations.
    ct=max(thrust_coefficient,1e-12)
    induced=brentq(lambda value:2*value*np.hypot(mu,value+uz)-ct,0,max(1.,abs(uz)+1),xtol=1e-12)
    total=induced+uz;vt=max(float(np.hypot(mu,total)),1e-10)
    ve=(mu*mu+total*(total+induced))/vt
    # Restrict continuation for undefined wake coefficients; final domain is checked.
    ve=max(ve,1e-8);chi=np.arctan2(mu,max(total,1e-10));x=np.tan(chi/2)
    h=15*pi/64*x
    L=np.array([[.5,h,0],[-h,2*(1-x*x),0],[0,0,2*(1+x*x)]])
    forcing=np.r_[thrust_coefficient,transform@pressure_moments]
    target=(L@forcing)/np.array([vt,ve,ve])
    current=np.r_[inflow[0],transform@inflow[1:]]
    residual=current-target
    if dynamic:
        # Original GenHel pressure-moment normalization, reordered [0,c,s].
        # Fixed shaft states: rotate the frozen-flow operator, no wake-curvature term.
        rate=omega*np.array([75*pi/128,45*pi/16,45*pi/16])*(forcing-np.linalg.solve(L,np.array([vt,ve,ve])*current))
        residual=np.r_[rate[0],transform.T@rate[1:]]
    return residual,dict(momentum_induced=induced,total_axial_ratio=total,mu=mu,
                               mass_flow_mean=vt,mass_flow_harmonic=ve,wake_skew_rad=float(chi))


class SteadyRotor:
    def __init__(self, rotor, config, rotation_sign=1, azimuth_stations=36):
        self.rotor=rotor;self.config=config
        self.kernel=AzimuthRotor(rotor,azimuth_stations,rotation_sign,config['hinge_offset_m'],
                                 np.tan(np.deg2rad(config.get('delta3_deg',0))))
        self.scale=rotor.density*pi*rotor.radius**2*(rotor.omega*rotor.radius)**2
        self.fixed=config['mode']=='fixed'

    def initial(self, thrust_guess=None):
        thrust=thrust_guess if thrust_guess is not None else .007*self.scale
        return np.r_[np.sqrt(max(thrust/self.scale,1e-6)/2),0,0,
                     np.deg2rad(self.config.get('precone_deg',0)),0,0]

    def bounds(self):
        limit=np.deg2rad(self.config['max_flap_deg'])
        return np.r_[1e-6,-.5,-.5,-limit,-limit,-limit],np.r_[.5,.5,.5,limit,limit,limit]

    def evaluate(self, state, controls, velocity, gravity=(0,0,-9.80665), strict=False, *, body_rates=(0,0,0), require_equilibrium=True):
        state=np.asarray(state,dtype=float);inflow,flap=state[:3],state[3:]
        data=self.kernel.elements(controls,inflow,flap,velocity,strict=strict,body_rates=body_rates)
        thrust=data['force'][2];ct=thrust/self.scale
        ir,diagnostic=pitt_peters(inflow,np.asarray(velocity)/(self.rotor.omega*self.rotor.radius),
                                  ct,data['pressure_moments']/(self.scale*self.rotor.radius))
        cfg=self.config
        if self.fixed:
            residual_flap=flap-np.deg2rad([cfg['precone_deg'],0,0])
            harmonic_defect=0.
        else:
            inertia=cfg['inertia_kg_m2'];m1=cfg['first_mass_moment_kg_m'];omega=self.rotor.omega
            beta=data['beta']
            centrifugal=omega**2*np.sin(beta)*(inertia*np.cos(beta)+cfg['hinge_offset_m']*m1)
            spring=cfg['spring_nm_rad']*(beta-np.deg2rad(cfg['precone_deg']))
            damping=cfg['damper_nms_rad']*data['beta_dot']
            gravity_moment=m1*(data['normal']@np.asarray(gravity))
            # Constant body-rate Coriolis/centripetal terms projected at the hinge.
            # Hub/shaft acceleration coupling is omitted in the reduced model.
            n=data['normal'];er=self.kernel.er;et=self.kernel.et
            b=np.cos(beta)[:,None]*er;b[:,2]=np.sin(beta)
            weighted_position=cfg['hinge_offset_m']*m1*er+inertia*b
            weighted_velocity=omega*(cfg['hinge_offset_m']*m1+inertia*np.cos(beta))[:,None]*et+inertia*data['beta_dot'][:,None]*n
            rate_accel=2*np.cross(body_rates,weighted_velocity)+np.cross(body_rates,np.cross(body_rates,weighted_position))
            rate_moment=np.einsum('ij,ij->i',n,rate_accel)
            defect=(inertia*data['beta_ddot']+centrifugal+spring+damping+rate_moment-data['flap_moment']-gravity_moment)/(inertia*omega**2)
            residual_flap=np.array([1,2,2])*np.mean(defect[:,None]*self.kernel.harmonics,axis=0)
            harmonic_defect=float(np.sqrt(np.mean(defect**2)))
        residual=np.r_[ir,residual_flap]
        if strict:
            if ct<=0 or data['power']<=0:raise ValueError('整机旋翼要求正推力和正轴功率。')
            if diagnostic['total_axial_ratio']<=0:raise ValueError('入流超出正贯流分支；未实现下降/涡环态。')
            if np.max(abs(data['beta']))>np.deg2rad(cfg['max_flap_deg'])+1e-8:
                raise ValueError('实际挥舞角超出机型限制。')
            if np.max(data['mach'])>1 and self.rotor.airfoil_grid is None:
                raise ValueError('无Mach维度的极曲线不支持超声速叶素。')
            checked=residual if require_equilibrium else residual_flap
            if np.max(abs(checked))>1e-6:raise ValueError('旋翼内部入流/挥舞残差未收敛。')
        diagnostic.update(internal_max_residual=float(np.max(abs(residual))),
            omitted_flap_harmonics_rms=harmonic_defect,alpha_min_deg=float(data['alpha_deg'].min()),
            alpha_max_deg=float(data['alpha_deg'].max()),mach_max=float(data['mach'].max()),
            flap_peak_deg=float(np.rad2deg(abs(data['beta']).max())),reverse_flow_fraction=data['reverse_flow_fraction'])
        return residual,data,diagnostic

    def solve(self, controls, velocity, gravity=(0,0,-9.80665), initial=None):
        low,high=self.bounds();seed=self.initial() if initial is None else initial
        fit=least_squares(lambda x:self.evaluate(x,controls,velocity,gravity)[0],
                          np.clip(seed,low+1e-9,high-1e-9),bounds=(low,high),x_scale='jac',
                          ftol=1e-11,gtol=1e-11,xtol=1e-11,max_nfev=100)
        residual,data,diagnostic=self.evaluate(fit.x,controls,velocity,gravity,strict=True)
        return fit.x,data,diagnostic
