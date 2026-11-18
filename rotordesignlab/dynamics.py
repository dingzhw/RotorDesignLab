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
    size = len(plant.state)
    steps = getattr(plant, 'state_steps', STATE_STEPS)
    a, b = np.empty((size, size)), np.empty((size, 4))
    for index,h in enumerate(steps*factor):
        offset = np.zeros(size)
        offset[index] = h
        a[:,index]=(plant.rhs(plant.state+offset,plant.controls)-plant.rhs(plant.state-offset,plant.controls))/(2*h)
    for index,h in enumerate(getattr(plant, 'control_steps', CONTROL_STEPS)*factor):
        offset=np.zeros(4);offset[index]=h
        b[:,index]=(plant.rhs(plant.state,plant.controls+offset)-plant.rhs(plant.state,plant.controls-offset))/(2*h)
    return a,b


def derivative_check(a,b,refa,refb,state_scale=None):
    # Compare effects in dimensionless design perturbation coordinates.
    # Row/column minimum keeps body derivatives from being hidden by fast inflow
    # rows. Exclude only <0.1% of the smaller peak, with a 1e-7/s absolute floor.
    scale = STATE_SCALE if state_scale is None else np.asarray(state_scale)
    uscale = np.full(4,np.deg2rad(1.))
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


def modes(a, state_names=None):
    """Keep eigenvalues even when an eigenvector basis cannot support attribution."""
    names = STATES if state_names is None else state_names
    values, right = np.linalg.eig(a)
    condition = float(np.linalg.cond(right))
    limit = 1e8
    left = None
    reason = ''
    if not np.isfinite(condition) or condition > limit:
        reason = '特征向量基病态；参与因子不可用。'
    else:
        try:
            left = np.linalg.inv(right)
        except np.linalg.LinAlgError:
            reason = '特征向量基不可逆；参与因子不可用。'
    answer = []
    scale = np.linalg.norm(a, 2)
    for i, value in enumerate(values):
        vector = right[:, i]
        denominator = max((scale + abs(value)) * np.linalg.norm(vector), np.finfo(float).tiny)
        residual = float(np.linalg.norm(a @ vector - value * vector) / denominator)
        available = left is not None and np.isfinite(residual) and residual <= 1e-10
        repeated = np.count_nonzero(np.isclose(values, value, rtol=1e-8, atol=1e-10)) > 1
        weights = np.zeros(len(values))
        note = reason
        if available:
            weights = abs(vector * left[i, :])
            available = bool(np.isfinite(weights).all() and weights.sum() > 0)
            if available:
                weights /= weights.sum()
                note = '重根的单根参与因子依赖所选特征向量基。' if repeated else ''
        if not available and not note:
            note = '特征残差或参与因子数值检查失败；参与因子不可用。'
        wn = abs(value)
        behavior = 'unstable' if value.real > 0 else 'stable'
        if wn < 1e-7:
            behavior = 'kinematic_neutral' if available and weights[8] > .9 else 'near_neutral'
        answer.append(dict(
            real=float(value.real), imag=float(value.imag),
            damping_ratio=float(-value.real / wn) if wn > 1e-7 else None,
            period_s=float(2 * np.pi / abs(value.imag)) if abs(value.imag) > 1e-7 else None,
            e_folding_time_s=float(1 / abs(value.real)) if abs(value.real) > 1e-7 else None,
            behavior=behavior,
            participation={names[j]: float(weights[j]) for j in np.argsort(weights)[-4:][::-1]} if available else {},
            participation_status='available' if available else 'unavailable',
            participation_note=note, repeated_eigenvalue=bool(repeated),
            eigenvector_condition=condition if np.isfinite(condition) else None,
            eigenvector_condition_limit=limit, eigenpair_relative_residual=residual))
    return sorted(answer, key=lambda item: (-item['real'], -item['imag']))


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
    def __init__(self,message,history,state_count=15):
        super().__init__(message)
        self.history = np.asarray(history).reshape((-1, 1+2*state_count))


def step_response(plant, a, b, control_index, amplitude_deg, duration, step, *, perturbation=None):
    """Shared waveform, nonlinear RK4 and linear propagation, split at input knots.

    The historical API still defaults to a step at zero. Constant-input pieces
    use the exact linear exponential; smooth pulse pieces use matching RK stages.
    Rows retain the original time + 15 nonlinear + 15 linear column layout.
    """
    from .perturbation import Perturbation
    wave = (perturbation or Perturbation(amplitude_deg=amplitude_deg)).validate(duration)
    count = round(duration / step)
    if count < 1 or abs(duration / step - count) > 1e-8:
        raise ValueError('时长必须为步长整数倍。')
    events = [v for v in wave.breakpoints() if 0 <= v <= duration]
    times = [t for t in np.arange(count + 1) * step if not any(abs(t - e) < 1e-12 for e in events)]
    times = sorted([*times, *events])
    size = len(plant.state)
    linear = np.zeros(size)
    nonlinear = plant.state.copy()
    transitions = {}
    rows = []

    def input_at(time):
        du = np.zeros(4)
        du[control_index] = np.deg2rad(wave.value_deg(time))
        return du

    for index, time in enumerate(times):
        first_input = input_at(time)
        try:
            k1 = plant.rhs(nonlinear, plant.controls + first_input)
        except ValueError as error:
            raise ResponseDomainError(f't={time:g}s状态超出支持域：{error}', rows, size) from error
        rows.append(np.r_[time, nonlinear - plant.state, linear])
        if index == len(times) - 1:
            break
        end = times[index + 1]
        h = end - time
        middle_input = input_at(time + h / 2)
        # The ending RK stage belongs to the interval on the LEFT of a jump.
        endpoint = np.nextafter(end, -np.inf) if wave.kind != 'pulse' and end in events else end
        last_input = input_at(endpoint)
        try:
            k2 = plant.rhs(nonlinear + h * k1 / 2, plant.controls + middle_input)
            k3 = plant.rhs(nonlinear + h * k2 / 2, plant.controls + middle_input)
            k4 = plant.rhs(nonlinear + h * k3, plant.controls + last_input)
        except ValueError as error:
            raise ResponseDomainError(f't={time:g}s之后积分失败：{error}', rows, size) from error
        nonlinear += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        if wave.kind != 'pulse':
            key = round(h, 12)
            if key not in transitions:
                transitions[key] = expm(np.block([[a, b], [np.zeros((4, size+4))]]) * h)
            transition = transitions[key]
            linear = transition[:size, :size] @ linear + transition[:size, size:] @ first_input
        else:
            l1 = a @ linear + b @ first_input
            l2 = a @ (linear + h * l1 / 2) + b @ middle_input
            l3 = a @ (linear + h * l2 / 2) + b @ middle_input
            l4 = a @ (linear + h * l3) + b @ last_input
            linear += h * (l1 + 2 * l2 + 2 * l3 + l4) / 6
    return np.asarray(rows)
