"""Simultaneous 6-component aircraft / 12-state steady-rotor equilibrium."""
from math import pi
from time import perf_counter
import numpy as np
from scipy.optimize import least_squares

from .aircraft import read_aircraft,require_analysis,snapshot_aircraft,AERO_KEYS
from .airframe import airframe_loads,body_to_ned,flight_velocity
from .azimuth import rotor_basis
from .cases import numeric,read_rotor,write_csv,write_json
from .hover import atmosphere,apply_design,G,VARIABLES
from .steady_rotor import SteadyRotor

CONTROL_NAMES=['main_collective_deg','main_cos_deg','main_sin_deg','tail_collective_deg','roll_deg','pitch_deg']


class TrimSystem:
    def __init__(self,aircraft,base,case):
        self.aircraft=aircraft;self.case=case;self.air=atmosphere(case['altitude_m'])
        self.weight=aircraft['mass_properties']['mass_kg']*G
        self.selected={r['role']:r for r in aircraft['rotors']};self.rotors={};self.bases={}
        for role,data in self.selected.items():
            spec={key:data[key] for key in ('blade_count','radius_m','pitch_reference_r_over_R','geometry_csv','polar_csv','polar_json',*AERO_KEYS) if key in data}
            spec.update(data['defaults'],axial_speed_m_s=0,density_kg_m3=self.air['density_kg_m3'],speed_of_sound_m_s=self.air['speed_of_sound_m_s'],
                        dynamic_viscosity_pa_s=self.air['dynamic_viscosity_pa_s'])
            model,_=read_rotor(spec,base)
            self.rotors[role]=SteadyRotor(model,data['flight']['flapping'],data['rotation_sign'],case['azimuth_stations'])
            self.bases[role]=rotor_basis(data['thrust_axis_body'],data['flight']['x_reference_body'])
        self.Rmain=self.selected['main']['radius_m']

    def bounds(self):
        main,tail=self.selected['main'],self.selected['tail'];cfg=self.aircraft['trim']
        ranges=[main['limits']['collective_deg'],main['flight']['cyclic_cos_deg'],main['flight']['cyclic_sin_deg'],
                tail['limits']['collective_deg'],cfg['roll_deg'],cfg['pitch_deg']]
        low,high=np.deg2rad(np.array(ranges).T)
        for role in ('main','tail'):
            l,h=self.rotors[role].bounds();low=np.r_[low,l];high=np.r_[high,h]
        return low,high

    def initial(self):
        m,t=self.selected['main'],self.selected['tail']
        controls=np.deg2rad([m['defaults']['collective_deg'],0,0,t['defaults']['collective_deg'],-2,0])
        return np.r_[controls,self.rotors['main'].initial(self.weight),self.rotors['tail'].initial()]

    def evaluate(self,x,strict=False):
        x=np.asarray(x,dtype=float)
        roll,pitch=x[4:6];R=body_to_ned(roll,pitch)
        velocity,velocity_valid=flight_velocity(self.case['speed_m_s'],self.case['climb_m_s'],roll,pitch)
        residual,data=self.loads(x,velocity,strict=strict)
        if strict:
            if not velocity_valid:raise ValueError('给定姿态无法满足无侧滑直线爬升运动学。')
            if np.max(abs(residual[:6]))>1e-4:raise ValueError('六分量配平残差未收敛。')
        return residual,data

    def loads(self,x,velocity,body_rates=(0,0,0),strict=False,require_equilibrium=True):
        """Common component loads for trim and the reduced dynamic model."""
        R=body_to_ned(*x[4:6]);gravity=R.T@np.array([0,0,G]);F=self.weight/G*gravity;M=np.zeros(3)
        internal=[];items={};rotor_data={};cg=np.asarray(self.aircraft['mass_properties']['cg_m'])
        for role,start,controls in [('main',6,x[:3]),('tail',12,np.array([x[3],0,0]))]:
            basis=self.bases[role];model=self.rotors[role];data=self.selected[role]
            try:
                hub_velocity=velocity+np.cross(body_rates,np.asarray(data['position_m'])-cg)
                residual,loads,diag=model.evaluate(x[start:start+6],controls,basis.T@hub_velocity,basis.T@gravity,strict,
                    body_rates=basis.T@np.asarray(body_rates),require_equilibrium=require_equilibrium)
            except ValueError as error:
                raise ValueError(role+': '+str(error)) from error
            internal.extend(residual);f=basis@loads['force'];m=basis@loads['moment']+np.cross(np.asarray(data['position_m'])-cg,f)
            F+=f;M+=m
            items[role]=dict(force_body_n=f.tolist(),moment_cg_body_nm=m.tolist(),power_w=loads['power'],
                             thrust_n=float(loads['force'][2]),torque_nm=loads['torque'],diagnostics=diag,
                             inflow=x[start:start+3].tolist(),flap_deg=np.rad2deg(x[start+3:start+6]).tolist())
            rotor_data[role]=loads
        induced=self.rotors['main'].rotor.omega*self.Rmain*x[6]*self.bases['main'][:,2]
        tail_induced=self.rotors['tail'].rotor.omega*self.selected['tail']['radius_m']*x[12]*self.bases['tail'][:,2]
        extra=airframe_loads(self.aircraft,velocity,self.air['density_kg_m3'],induced,strict,body_rates=body_rates,tail_induced_velocity_body=tail_induced)
        for item in extra.values():F+=item['force_body_n'];M+=item['moment_cg_body_nm']
        items.update(extra)
        # Explicit residual download coefficient, separate from fuselage wake loads.
        download=self.aircraft['hover']['download_fraction']*items['main']['thrust_n']
        df=-download*self.bases['main'][:,2];F+=df
        items['download']=dict(force_body_n=df.tolist(),moment_cg_body_nm=[0,0,0],power_w=0)
        outer=np.r_[F/self.weight,M/(self.weight*self.Rmain)]
        if strict:
            if items['main']['diagnostics']['mu']>.25+1e-9:raise ValueError('主桨推进比超出μ≤0.25范围。')
        return np.r_[outer,10*np.array(internal)],dict(components=items,force=F,moment=M,velocity=velocity,rotor_data=rotor_data)


def run_trim(case,base,output):
    started=perf_counter()
    allowed={'schema_version','model','analysis','aircraft_json','speed_m_s','climb_m_s','requested_duration_s',
             'radial_stations','azimuth_stations','cg_x_m','initial_state',*VARIABLES}
    if set(case)-allowed:raise ValueError(f'配平工况未识别字段：{sorted(set(case)-allowed)}')
    if not isinstance(case.get('aircraft_json'),str):raise ValueError('需要aircraft_json。')
    for key,bounds in [('speed_m_s',(0,150)),('climb_m_s',(0,15)),('altitude_m',(0,11000)),('requested_duration_s',(.001,1e9))]:numeric(case,key,*bounds)
    case=dict(case,azimuth_stations=case.get('azimuth_stations',36))
    numeric(case,'azimuth_stations',12,720,integer=True)
    path=(base/case['aircraft_json']).resolve();aircraft=read_aircraft(path);require_analysis(aircraft,'trim')
    if 'cg_x_m' in case:aircraft['mass_properties']['cg_m'][0]=numeric(case,'cg_x_m',-100,100)
    apply_design(aircraft,case)
    saved=snapshot_aircraft(aircraft,path.parent,output);snapshot=dict(case,aircraft_json='aircraft.json')
    write_json(output/'case.json',snapshot)
    plant=aircraft['powerplant'];altitude=case['altitude_m']
    if not plant['altitude_m'][0]<=altitude<=plant['altitude_m'][-1]:raise ValueError('高度超出可用功率曲线范围。')
    system=TrimSystem(saved,output,case);low,high=system.bounds()
    seed=system.initial()
    if 'initial_state' in case:
        values=case['initial_state']
        if (not isinstance(values,list) or len(values)!=18 or
            any(type(v) not in (int,float) or not np.isfinite(v) for v in values)):
            raise ValueError('initial_state需要18个有限数值：6个弧度操纵/姿态及两桨各6个稳态参数。')
        seed=np.asarray(values,dtype=float)
    initial_seed=np.clip(seed,low+1e-8,high-1e-8)
    fit=least_squares(lambda x:system.evaluate(x)[0],initial_seed,bounds=(low,high),x_scale='jac',
                      ftol=1e-10,xtol=1e-10,gtol=1e-10,max_nfev=120)
    residual,data=system.evaluate(fit.x)
    near_limits=[name for name,value,lo,hi in zip(CONTROL_NAMES,fit.x[:6],low[:6],high[:6])
                 if min(value-lo,hi-value)<np.deg2rad(.01)]
    diagnostic=dict(nfev=fit.nfev,message=str(fit.message),initial_state=initial_seed.tolist(),
        solved_state=fit.x.tolist(),scaled_force_moment_residual=residual[:6].tolist(),
        rotor_internal_residual=(residual[6:]/10).tolist(),near_limits=near_limits,elapsed_s=perf_counter()-started)
    diagnostic['rotors']={role:data['components'][role]['diagnostics'] for role in ('main','tail')}
    write_json(output/'trim-diagnostics.json',diagnostic)
    write_csv(output/'residuals.csv',['component','scaled_residual'],zip(['Fx','Fy','Fz','Mx','My','Mz'],residual[:6]))
    try:system.evaluate(fit.x,strict=True)
    except ValueError as error:
        numerical=np.max(abs(residual[:6]))>1e-4 or np.max(abs(residual[6:]/10))>1e-6
        return dict(status='failed',solver_status='not_converged' if numerical else 'converged',analysis='trim',
            support_status='not_established' if numerical else 'outside_implemented_domain',
            design_limits_status='not_evaluated',evidence_status='model_estimate',diagnostics=diagnostic,
            failure_kind=('control_limited' if near_limits else 'residual_not_converged') if numerical else 'outside_supported_domain',
            error=('配平方程未收敛；最终试探状态检查：' if numerical else '')+str(error)),snapshot
    controls=dict(zip(CONTROL_NAMES,np.rad2deg(fit.x[:6]).tolist()))
    margins={name:dict(to_lower=float(np.rad2deg(value-lo)),to_upper=float(np.rad2deg(hi-value)))
             for name,value,lo,hi in zip(CONTROL_NAMES,fit.x[:6],low[:6],high[:6])}
    required=plant['accessory_power_w'];violations=[];loss=0
    for role in ('main','tail'):
        item=data['components'][role];spec=system.selected[role];eff=spec['transmission_efficiency']
        required+=item['power_w']/eff;loss+=item['power_w']*(1/eff-1)
        for key in ('power_w','torque_nm'):
            if key in spec['limits'] and item[key]>spec['limits'][key]:violations.append(role+'_'+key+'_exceeded')
    continuous=float(np.interp(altitude,plant['altitude_m'],plant['continuous_power_w']))
    short=float(np.interp(altitude,plant['altitude_m'],plant['short_time_power_w']))
    applicable=case['requested_duration_s']<=plant['short_time_duration_s']
    margin=(short if applicable else continuous)-required
    if margin<0:violations.append('requested_duration_power_exceeded')
    saturated=[key for key,m in margins.items() if min(m.values())<.01]
    violations.extend(key+'_at_limit' for key in saturated)
    summary=dict(speed_m_s=case['speed_m_s'],climb_m_s=case['climb_m_s'],altitude_m=altitude,
        mass_kg=aircraft['mass_properties']['mass_kg'],required_power_w=required,transmission_loss_w=loss,
        accessory_power_w=plant['accessory_power_w'],continuous_margin_w=continuous-required,
        short_time_margin_w=short-required,duration_margin_w=margin,
        max_scaled_residual=float(np.max(abs(residual[:6]))),max_internal_residual=float(np.max(abs(residual[6:]/10))),**controls)
    for role in ('main','tail'):
        item=data['components'][role]
        summary.update({role+'_'+k:item[k] for k in ('thrust_n','torque_nm','power_w')})
    for role,loads in data['rotor_data'].items():
        kernel=system.rotors[role].kernel
        rows=((float(psi*180/pi),float(radius),*[float(loads[key][i,j]) for key in ('ut','up','alpha_deg','mach','cl','cd','induced_m_s')])
              for i,psi in enumerate(kernel.psi) for j,radius in enumerate(kernel.r))
        write_csv(output/f'{role}-elements.csv',['azimuth_deg','radius_m','ut_m_s','up_m_s','alpha_deg','mach','cl','cd','induced_m_s'],rows)
    write_csv(output/'trim.csv',['quantity','value'],summary.items())
    result=dict(status='converged',solver_status='converged',analysis='trim',summary=summary,
        feasible=not violations,support_status='within_implemented_steady_domain',design_limits_status='exceeded' if violations else 'within_supplied_limits',
        evidence_status='model_estimate',violations=violations,control_margins_deg=margins,components=data['components'],
        residual_force_body_n=data['force'].tolist(),residual_moment_body_nm=data['moment'].tolist(),
        velocity_body_m_s=data['velocity'].tolist(),diagnostics=diagnostic,
        short_time_rating_applicable=applicable,elapsed_s=perf_counter()-started,
        backend='Python / azimuth blade elements + steady PP + first harmonic flap + six-component trim',
        warnings=['旋翼模型估算，稳态一阶挥舞；未包含高阶桨叶运动、弹性、旋流和主尾桨干扰。',
                  '下载/尾翼下洗采用输入显式系数；数据来源与工程估计见机型。'])
    lines=['# 整机六分量配平','',f"求解收敛；数据域：{result['support_status']}；限制：{result['design_limits_status']}；证据：模型估算。",'',
           '|量|值|','|---|---:|']+[f'|{k}|{v:.8g}|' for k,v in summary.items()]
    lines+=['','控制定义与双向余量见result.json；旋翼内部残差与初值见trim-diagnostics.json。',
             '零侧滑直线前飞，纯垂直爬升保留姿态变换产生的机体系侧向速度。全输入可用run case.json复算。']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result,snapshot
