"""Isolated rotor with 3-D air-relative-to-hub flow and azimuth blade elements.

The existing steady rotor kernel takes hub-relative-to-air velocity; this adapter
reverses the input vector once and transforms it from body to rotor coordinates.
No airframe loads, trim constraints, swirl or spanwise aerodynamic force are added.
"""
from dataclasses import replace
from math import pi
import numpy as np
from scipy.optimize import brentq

from .aircraft import prepare, OPERATING_KEYS, AERO_KEYS
from .azimuth import rotor_basis
from .cases import numeric, write_csv, write_json
from .steady_rotor import SteadyRotor

SPATIAL_KEYS = {'flow_body_m_s','cyclic_cos_deg','cyclic_sin_deg','azimuth_stations','flapping_model'}
COMMON_KEYS = {'schema_version','model','aircraft_json','rotor_id','density_kg_m3','target',*OPERATING_KEYS,*AERO_KEYS}


def setup(case, selected, rotor):
    raw=case.get('flow_body_m_s')
    if (not isinstance(raw,list) or len(raw)!=3 or
        any(type(v) not in (int,float) or not np.isfinite(v) for v in raw)):
        raise ValueError('三方向来流必须为机体系X/Y/Z三个有限数值，单位m/s。')
    flow=np.array(raw,dtype=float)
    if np.linalg.norm(flow)>150:raise ValueError('来流合速度超过本入口150 m/s的输入范围。')
    flight=selected.get('flight',{})
    reference=flight.get('x_reference_body')
    if reference is None:
        reference=next(axis for axis in ([1,0,0],[0,1,0],[0,0,1])
                       if abs(np.dot(axis,selected['thrust_axis_body']))<.99)
    basis=rotor_basis(selected['thrust_axis_body'],reference)
    velocity=-basis.T@flow
    if velocity[2]<-1e-9:
        raise ValueError('沿正推力轴的来流分量为正，属于反向贯流/下降分支；本入口目前支持悬停、正贯流和盘面内来流。')
    na=numeric(dict(azimuth_stations=case.get('azimuth_stations',36)),'azimuth_stations',12,720,integer=True)
    cyclic=[numeric(dict(value=case.get(key,0.)), 'value',-30,30) for key in ('cyclic_cos_deg','cyclic_sin_deg')]
    for key,value in zip(('cyclic_cos_deg','cyclic_sin_deg'),cyclic):
        if key in flight and not flight[key][0]<=value<=flight[key][1]:
            raise ValueError(('cos' if 'cos' in key else 'sin')+'周期变距超过机型限位。')
    flap_mode=case.get('flapping_model','fixed')
    if flap_mode not in ('fixed','aircraft'):raise ValueError('挥舞设置应选择固定桨叶或使用机型参数。')
    if flap_mode=='aircraft':
        if 'flapping' not in flight:raise ValueError('此旋翼缺少挥舞参数，请使用固定桨叶或补齐机型。')
        config=dict(flight['flapping'])
        if config['mode']=='hinged':
            missing=[k for k in ('inertia_kg_m2','first_mass_moment_kg_m','spring_nm_rad','damper_nms_rad') if k not in config]
            if missing:raise ValueError('铰接挥舞需补齐桨叶惯量、质量一阶矩、弹簧刚度和阻尼。')
    else:
        cone=rotor.precone_deg
        config=dict(mode='fixed',hinge_offset_m=0.,precone_deg=cone,max_flap_deg=max(15.,abs(cone)))
    return flow,basis,velocity,na,cyclic,config


def evaluate(rotor,selected,setup_values):
    flow,basis,velocity,na,cyclic,config=setup_values
    mu=np.linalg.norm(velocity[:2])/(rotor.omega*rotor.radius)
    if mu>.25+1e-12:raise ValueError(f'盘面内推进比 μ={mu:.4f} 超过当前模型范围0.25。')
    model=SteadyRotor(rotor,config,selected['rotation_sign'],na)
    controls=np.deg2rad([rotor.collective_deg,*cyclic])
    state,loads,diagnostic=model.solve(controls,velocity,gravity=basis.T@np.array([0,0,9.80665]))
    if rotor.airfoil_grid is None and np.max(np.hypot(loads['ut'],loads['up']))>250:
        raise ValueError('无Mach维度的翼型表仅支持当地叶素合速度不超过250 m/s。')
    if not np.isfinite(loads['force']).all() or not np.isfinite(loads['moment']).all():
        raise ValueError('旋翼载荷出现非有限值。')
    return model,state,loads,diagnostic


def inverse(rotor,selected,setup_values,target):
    if not isinstance(target,dict) or set(target)-{'thrust_n','solve_for','bounds'}:
        raise ValueError('目标拉力设置包含未支持的字段。')
    thrust=numeric(target,'thrust_n',1e-9,1e10)
    variable=target.get('solve_for')
    if variable not in ('rpm','collective_deg'):raise ValueError('反求变量须为总距或转速。')
    bounds=target.get('bounds',selected['limits'][variable])
    if (not isinstance(bounds,list) or len(bounds)!=2 or
        any(type(v) not in (int,float) or not np.isfinite(v) for v in bounds) or
        not selected['limits'][variable][0]<=bounds[0]<bounds[1]<=selected['limits'][variable][1]):
        raise ValueError('反求上下限须递增并位于机型操纵范围内。')
    cache={};reasons=set()
    def residual(value):
        if value not in cache:
            changed=replace(rotor,**({'omega':value*pi/30} if variable=='rpm' else {variable:value}))
            try:cache[value]=(changed,evaluate(changed,selected,setup_values))
            except ValueError as error:reasons.add(str(error));cache[value]=None
        item=cache[value]
        return item[1][2]['force'][2]-thrust if item else float('nan')
    samples=np.linspace(*bounds,33);values=[residual(float(v)) for v in samples]
    roots=[float(x) for x,y in zip(samples,values) if abs(y)<max(1e-8,thrust*1e-10)]
    for a,b,fa,fb in zip(samples[:-1],samples[1:],values[:-1],values[1:]):
        if fa*fb<0:
            try:roots.append(float(brentq(residual,float(a),float(b),xtol=1e-9)))
            except ValueError:continue  # A data-domain gap must not become a solution.
    unique=[]
    for root in sorted(roots):
        if not unique or abs(root-unique[-1])>1e-7:unique.append(root)
    if not unique:raise ValueError('给定范围内未找到有效的目标拉力解。'+('；'.join(sorted(reasons)[:3])))
    if len(unique)!=1:raise ValueError('反求区间有多个解，请收窄总距或转速上下限。')
    value=unique[0];error=abs(residual(value))/thrust
    if not np.isfinite(error) or error>1e-6:raise ValueError('反求后的拉力未达到内部一致性容差。')
    solved,answer=cache[value]
    return solved,answer,dict(solve_for=variable,value=value,target_thrust_n=thrust,relative_thrust_error=error,
                              bounds=bounds,search_samples=len(samples))


def plot_elements(model,loads,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .presentation import configure_chinese_plots
    configure_chinese_plots()
    fig,panels=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    values=[loads['alpha_deg'],loads['element_force'][:,:,2]/model.kernel.dr]
    for panel,value,title,unit in zip(panels,values,['当地攻角','单片桨叶轴向气动力密度'],['攻角 / °','气动力 / (N/m)']):
        mesh=panel.pcolormesh(model.kernel.r/model.rotor.radius,np.rad2deg(model.kernel.psi),value,shading='auto')
        panel.set(xlabel='半径比 r/R',ylabel='方位角 ψ / °',title=title)
        fig.colorbar(mesh,ax=panel,label=unit)
    for extension in ('png','svg'):fig.savefig(output/f'azimuth.{extension}',dpi=150)
    plt.close(fig)


def run_spatial(case,base,output):
    unknown=set(case)-(COMMON_KEYS|SPATIAL_KEYS)
    if unknown:raise ValueError('三方向来流工况含未识别或轴流专用字段：'+', '.join(sorted(unknown)))
    rotor,aircraft,selected,snapshot=prepare({k:v for k,v in case.items() if k in COMMON_KEYS},base,output)
    snapshot.pop('axial_speed_m_s',None)
    snapshot.update({k:v for k,v in case.items() if k in SPATIAL_KEYS})
    snapshot.setdefault('flapping_model','fixed');snapshot.setdefault('azimuth_stations',36)
    for key in ('cyclic_cos_deg','cyclic_sin_deg'):snapshot.setdefault(key,0.)
    write_json(output/'case.json',snapshot)
    setup_values=setup(snapshot,selected,rotor)
    target_solution=None
    if 'target' in case:rotor,answer,target_solution=inverse(rotor,selected,setup_values,case['target'])
    else:answer=evaluate(rotor,selected,setup_values)
    model,state,loads,diagnostic=answer
    flow,basis,velocity,na,cyclic,config=setup_values
    F=basis@loads['force'];M=basis@loads['moment']
    arm=np.asarray(selected['position_m'])-np.asarray(aircraft['mass_properties']['cg_m'])
    Mcg=M+np.cross(arm,F)
    scale=rotor.density*pi*rotor.radius**2*(rotor.omega*rotor.radius)**2
    summary=dict(thrust_n=float(loads['force'][2]),torque_nm=loads['torque'],power_w=loads['power'],
        rpm=rotor.omega*30/pi,collective_deg=rotor.collective_deg,
        thrust_coefficient=float(loads['force'][2]/scale),torque_coefficient=loads['torque']/(scale*rotor.radius),
        power_coefficient=loads['power']/(scale*rotor.omega*rotor.radius),tip_speed_m_s=rotor.omega*rotor.radius,
        inflow_mean=float(state[0]),inflow_cos=float(state[1]),inflow_sin=float(state[2]),
        induced_speed_m_s=float(state[0]*rotor.omega*rotor.radius),
        alpha_min_deg=diagnostic['alpha_min_deg'],alpha_max_deg=diagnostic['alpha_max_deg'],
        mu=diagnostic['mu'],flap_coning_deg=float(np.rad2deg(state[3])),
        flap_cos_deg=float(np.rad2deg(state[4])),flap_sin_deg=float(np.rad2deg(state[5])))
    margins={k:v-summary[k] for k,v in selected['limits'].items() if k in ('power_w','torque_nm')}
    within=all(v>=0 for v in margins.values())
    installation=dict(force_body_n=F.tolist(),moment_hub_body_nm=M.tolist(),moment_cg_body_nm=Mcg.tolist(),
        force_rotor_n=loads['force'].tolist(),moment_hub_rotor_nm=loads['moment'].tolist(),
        rotor_to_body=basis.tolist(),rotor_id=selected['id'],aircraft_id=aircraft['id'],margins=margins,
        within_supplied_limits=within,scope='revolution-mean aerodynamic loads only; no whole-aircraft trim')
    k=model.kernel;force=loads['element_force'];moment=np.cross(loads['position'],force)
    dT=rotor.blades*np.mean(force[:,:,2],axis=0);dQ=-selected['rotation_sign']*rotor.blades*np.mean(moment[:,:,2],axis=0)
    write_csv(output/'radial_loads.csv',('r_m','dr_m','chord_m','dthrust_n','dtorque_nm','thrust_n_per_m','torque_nm_per_m'),
              zip(k.r,k.dr,k.chord,dT,dQ,dT/k.dr,dQ/k.dr))
    keys=('ut','up','alpha_deg','mach','cl','cd','induced_m_s')
    write_csv(output/'azimuth_loads.csv',('azimuth_deg','r_m',*keys,'fx_rotor_n','fy_rotor_n','fz_rotor_n'),
        ((float(np.rad2deg(psi)),float(radius),*[float(loads[key][i,j]) for key in keys],*force[i,j].tolist())
         for i,psi in enumerate(k.psi) for j,radius in enumerate(k.r)))
    write_csv(output/'rotor_loads.csv',('quantity','x','y','z'),
              [('force_body_n',*F),('moment_hub_body_nm',*M),('moment_cg_body_nm',*Mcg)])
    plot_elements(model,loads,output)
    solved=dict(snapshot,rpm=summary['rpm'],collective_deg=summary['collective_deg']);solved.pop('target',None)
    write_json(output/'solved-case.json',solved)
    notes=['# 孤立旋翼三方向来流结果','',f"拉力 {summary['thrust_n']:.6g} N；轴功率 {summary['power_w']/1000:.6g} kW。",
        f'输入来流（空气相对轮毂，机体系m/s）：{flow.tolist()}。',
        '机体系x向前、y向右、z向下；力矩按右手定则，CSV区分轮毂与重心。',
        '方位角从旋翼+x向+y增加；旋翼+z为正推力轴。输出为整转平均气动力，不含重力或整机配平。',
        '适用范围：正推力、正轴功率、非负正贯流、μ≤0.25，且所有当地攻角/Mach/Re在所给翼型数据域内。',
        '采用现有稳态三状态Pitt–Peters入流；不含展向气动力、尾流旋转、非定常失速或弹性桨叶。',
        '验证依据为软件/数值一致性和已有模型基准，当前三方向工况属于模型估算。']
    (output/'summary.md').write_text('\n\n'.join(notes)+'\n',encoding='utf-8')
    result=dict(summary=summary,installation=installation,diagnostics=diagnostic,feasible=within,
        backend='Python / azimuth blade elements / steady Pitt-Peters / '+config['mode'],
        solver_status='converged',support_status='within_implemented_steady_domain',
        design_limits_status='satisfied' if within else 'exceeded',evidence_status='model_estimate',
        flow_body_m_s=flow.tolist(),hub_velocity_rotor_m_s=velocity.tolist(),
        warnings=['整转平均孤立旋翼气动力；机身、尾翼、整机重力和旋翼间干扰未参与求解。',
                  '方位角模型采用三状态入流；轴流环带/Prandtl选项仅作用于独立的轴流性能模型。'])
    if target_solution:result['target_solution']=target_solution
    return result,snapshot
