"""Reduced open-loop dynamics: rigid body, dynamic inflow, algebraic flap.

Constant shaft RPM; no dynamic flap modes, rotor angular-momentum reaction,
hub-acceleration coupling, or wake-curvature dynamics. This is explicitly a
low-frequency model estimate, not the original Julia full-order system.
"""
import numpy as np
from scipy.linalg import block_diag,expm
from scipy.optimize import root
from .airframe import body_to_ned
from .hover import G
from .steady_rotor import pitt_peters

STATES=['u','v','w','p','q','r','phi','theta','psi',
        'main_lambda0','main_lambdac','main_lambdas','tail_lambda0','tail_lambdac','tail_lambdas']
UNITS=['m/s']*3+['rad/s']*3+['rad']*3+['1']*6
CONTROLS=['main_collective','main_cos','main_sin','tail_collective']
STATE_STEPS=np.array([1e-3]*3+[1e-4]*6+[1e-5]*6)
CONTROL_STEPS=np.full(4,1e-4)
APPARENT_MASS=np.array([128/(75*np.pi),16/(45*np.pi),16/(45*np.pi)])
STATE_SCALE=np.array([10.]*3+[.1]*6+[.05]*6)


def rigid_body_rhs(velocity,rates,angles,force,moment,mass,inertia):
    phi,theta,_=angles;s,c=np.sin(phi),np.cos(phi);ct=np.cos(theta)
    if abs(ct)<.2:raise ValueError('Euler姿态接近奇异，低频模型仅支持小扰动。')
    kinematics=np.array([[1,s*np.tan(theta),c*np.tan(theta)],[0,c,-s],[0,s/ct,c/ct]])
    return np.r_[np.asarray(force)/mass-np.cross(rates,velocity),
                 np.linalg.solve(inertia,np.asarray(moment)-np.cross(rates,inertia@rates)),kinematics@rates]


class ReducedDynamics:
    def __init__(self,system,trim_state,trim_velocity):
        self.system=system;self.trim=np.asarray(trim_state);self.controls=self.trim[:4].copy()
        props=system.aircraft['mass_properties'];self.mass=props['mass_kg'];self.inertia=np.asarray(props['inertia_cg_kg_m2'])
        self.state=np.r_[trim_velocity,np.zeros(3),self.trim[4:6],0.,self.trim[6:9],self.trim[12:15]]
        self.mass_matrix=block_diag(self.mass*np.eye(3),self.inertia,np.eye(3),
            *[np.diag(APPARENT_MASS/system.rotors[role].rotor.omega) for role in ('main','tail')])

    def evaluate(self,state,controls,strict=True):
        state=np.asarray(state);controls=np.asarray(controls)
        if state.shape!=(15,) or controls.shape!=(4,) or not np.isfinite(np.r_[state,controls]).all():
            raise ValueError('动态状态需要15个有限数，操纵需要4个有限弧度数。')
        velocity,rates,angles=state[:3],state[3:6],state[6:9]
        if strict:
            low,high=self.system.bounds()
            if np.any(controls<low[:4]) or np.any(controls>high[:4]):raise ValueError('动态操纵超出机型限位。')
            if np.any(angles[:2]<low[4:6]) or np.any(angles[:2]>high[4:6]):raise ValueError('动态姿态超出机型限制。')
        x=self.trim.copy();x[:4]=controls;x[4:6]=angles[:2];cg=np.asarray(self.system.aircraft['mass_properties']['cg_m'])
        gravity=body_to_ned(*angles[:2]).T@np.array([0,0,G]);details={}
        for role,ix,iy,control in [('main',6,9,controls[:3]),('tail',12,12,np.r_[controls[3],0,0])]:
            model=self.system.rotors[role];basis=self.system.bases[role];spec=self.system.selected[role]
            v=basis.T@(velocity+np.cross(rates,np.asarray(spec['position_m'])-cg));w=basis.T@rates
            inflow=state[iy:iy+3];x[ix:ix+3]=inflow
            if strict:
                low,high=model.bounds()
                if np.any(inflow<low[:3]) or np.any(inflow>high[:3]):raise ValueError(role+': 入流状态超出模型范围。')
            if model.fixed:flap=np.deg2rad([model.config['precone_deg'],0,0])
            else:
                def equation(flap):
                    return model.evaluate(np.r_[inflow,flap],control,v,basis.T@gravity,body_rates=w,require_equilibrium=False)[0][3:]
                fit=root(equation,self.trim[ix+3:ix+6],tol=1e-9)
                flap=fit.x
                if not np.isfinite(flap).all() or np.max(abs(equation(flap)))>1e-7:
                    raise ValueError(role+': 准定常挥舞代数方程未收敛。')
            x[ix+3:ix+6]=flap;details[role]=(v,inflow)
        _,data=self.system.loads(x,velocity,rates,strict,require_equilibrium=False)
        derivative=rigid_body_rhs(velocity,rates,angles,data['force'],data['moment'],self.mass,self.inertia)
        for role in ('main','tail'):
            model=self.system.rotors[role];loads=data['rotor_data'][role];v,inflow=details[role]
            rate,_=pitt_peters(inflow,v/(model.rotor.omega*model.rotor.radius),loads['force'][2]/model.scale,
                loads['pressure_moments']/(model.scale*model.rotor.radius),dynamic=True,omega=model.rotor.omega)
            derivative=np.r_[derivative,rate]
        return derivative,data

    def rhs(self,state,controls):return self.evaluate(state,controls)[0]


def central_derivatives(plant,factor=1.):
    a=np.empty((15,15));b=np.empty((15,4))
    for index,h in enumerate(STATE_STEPS*factor):
        offset=np.zeros(15);offset[index]=h
        a[:,index]=(plant.rhs(plant.state+offset,plant.controls)-plant.rhs(plant.state-offset,plant.controls))/(2*h)
    for index,h in enumerate(CONTROL_STEPS*factor):
        offset=np.zeros(4);offset[index]=h
        b[:,index]=(plant.rhs(plant.state,plant.controls+offset)-plant.rhs(plant.state,plant.controls-offset))/(2*h)
    return a,b


def derivative_check(a,b,refa,refb):
    # Compare effects in dimensionless design perturbation coordinates.
    # Row/column minimum keeps body derivatives from being hidden by fast inflow
    # rows. Exclude only <0.1% of the smaller peak, with a 1e-7/s absolute floor.
    scale=STATE_SCALE;uscale=np.full(4,np.deg2rad(1.))
    metrics={}
    for name,x,ref,colscale in [('A',a,refa,scale),('B',b,refb,uscale)]:
        current=x*colscale/scale[:,None];reference=ref*colscale/scale[:,None]
        row_peak=np.max(abs(reference),axis=1);column_peak=np.max(abs(reference),axis=0)
        floor=np.maximum(np.minimum(row_peak[:,None],column_peak[None,:])*.001,1e-7)
        active=abs(reference)>floor
        relative=abs(current-reference)/np.maximum(abs(reference),floor)
        metrics[name]=dict(max_major_relative_change=float(relative[active].max()) if active.any() else 0.,
            max_scaled_absolute_change=float(abs(current-reference).max()),major_entries=int(active.sum()),
            row_scaled_peak=row_peak.tolist(),column_scaled_peak=column_peak.tolist(),
            threshold_rule='max(0.001*min(row_peak,column_peak),1e-7) in scaled coordinates')
    metrics['passed']=max(metrics[k]['max_major_relative_change'] for k in ('A','B'))<=.02
    return metrics


def modes(a):
    values,right=np.linalg.eig(a);left=np.linalg.inv(right);answer=[]
    for i,value in enumerate(values):
        weights=abs(right[:,i]*left[i,:]);weights/=max(weights.sum(),1e-30)
        wn=abs(value);neutral=wn<1e-7
        answer.append(dict(real=float(value.real),imag=float(value.imag),
            damping_ratio=float(-value.real/wn) if wn>1e-7 else None,
            period_s=float(2*np.pi/abs(value.imag)) if abs(value.imag)>1e-7 else None,
            e_folding_time_s=float(1/abs(value.real)) if abs(value.real)>1e-7 else None,
            behavior=('kinematic_neutral' if weights[8]>.9 else 'near_neutral') if neutral else ('unstable' if value.real>0 else 'stable'),
            participation={STATES[j]:float(weights[j]) for j in np.argsort(weights)[-4:][::-1]}))
    return sorted(answer,key=lambda x:(-x['real'],-x['imag']))


def frequency_response(a,b,frequencies):
    rows=[]
    for frequency in frequencies:
        h=np.linalg.solve(1j*frequency*np.eye(len(a))-a,b)
        for j,control in enumerate(CONTROLS):
            for i in (0,1,2,3,4,5,6,7,8):
                gain=h[i,j]
                rows.append([frequency,STATES[i],control,float(abs(gain)),float(20*np.log10(max(abs(gain),1e-30))),
                             float(np.angle(gain,deg=True)),float(gain.real),float(gain.imag)])
    return rows


class ResponseDomainError(ValueError):
    def __init__(self,message,history):
        super().__init__(message);self.history=np.asarray(history)


def step_response(plant,a,b,control_index,amplitude_deg,duration,step):
    """Simultaneous nonlinear RK4 and exact constant-input linear propagation."""
    count=round(duration/step);times=np.arange(count+1)*step
    du=np.zeros(4);du[control_index]=np.deg2rad(amplitude_deg)
    transition=expm(np.block([[a,b],[np.zeros((4,19))]])*step)
    linear=np.zeros(15);nonlinear=plant.state.copy();rows=[]
    for i,t in enumerate(times):
        try:k1=plant.rhs(nonlinear,plant.controls+du)
        except ValueError as error:raise ResponseDomainError(f't={t:g}s状态超出支持域：{error}',rows) from error
        delta=nonlinear-plant.state;rows.append(np.r_[t,delta,linear])
        if i==count:break
        try:
            k2=plant.rhs(nonlinear+step*k1/2,plant.controls+du)
            k3=plant.rhs(nonlinear+step*k2/2,plant.controls+du)
            k4=plant.rhs(nonlinear+step*k3,plant.controls+du)
        except ValueError as error:raise ResponseDomainError(f't={t:g}s之后积分失败：{error}',rows) from error
        nonlinear+=step*(k1+2*k2+2*k3+k4)/6
        linear=transition[:15,:15]@linear+transition[:15,15:]@du
    return np.asarray(rows)
