"""Steady component loads and aircraft/rotor coordinate transformations."""
import numpy as np
from .azimuth import rotor_basis


def validate_trim_inputs(aircraft):
    missing=[]
    if 'trim' not in aircraft:missing.append('trim (attitude limits, fuselage and surfaces)')
    for rotor in aircraft['rotors']:
        flight=rotor.get('flight')
        if flight is None:missing.append(rotor['id']+'/flight');continue
        cfg=flight['flapping']
        if cfg['mode']=='hinged':
            missing.extend(rotor['id']+'/flight/flapping/'+key for key in
                ('inertia_kg_m2','first_mass_moment_kg_m','spring_nm_rad','damper_nms_rad') if key not in cfg)
        rotor_basis(rotor['thrust_axis_body'],flight['x_reference_body'])
        if abs(cfg['precone_deg'])>cfg['max_flap_deg']:raise ValueError('预锥超出挥舞限制。')
        for key in ('cyclic_cos_deg','cyclic_sin_deg'):
            if not -30<=flight[key][0]<0<flight[key][1]<=30:raise ValueError('周期变距区间需包含0且位于±30°内。')
    if missing:raise ValueError('整机配平缺少：'+'; '.join(missing))
    cfg=aircraft['trim']
    for key in ('roll_deg','pitch_deg'):
        if not -40<=cfg[key][0]<0<cfg[key][1]<=40:raise ValueError('姿态限制需包含0且位于±40°内。')
    fus=cfg['fuselage']
    tables=list(fus['wind_tables'].values()) if 'wind_tables' in fus else [fus['alpha_table'],fus['beta_table']]
    ids=[]
    for surface in cfg['surfaces']:
        ids.append(surface['id']);n=np.asarray(surface['normal_axis_body']);c=np.asarray(surface['chord_axis_body'])
        if not np.isclose(np.linalg.norm(n),1) or not np.isclose(np.linalg.norm(c),1) or abs(np.dot(c,n))>1e-8:
            raise ValueError('尾翼弦线与法向必须为正交单位向量。')
        tables.append(surface['polar'])
        if surface.get('reverse_flow_symmetry',False):
            polar=surface['polar']
            if polar['angle_deg'][0]!=-90 or polar['angle_deg'][-1]!=90 or max(abs(polar['cl'][0]),abs(polar['cl'][-1]))>1e-8:
                raise ValueError('反向流对称延拓要求±90°端点且端点CL=0。')
        if 'incidence_schedule' in surface:
            schedule=surface['incidence_schedule'];v=np.asarray(schedule['speed_m_s'])
            if np.any(np.diff(v)<=0) or len(v)!=len(schedule['angle_deg']):raise ValueError('尾翼调度速度需递增、与安装角等长。')
    if len(ids)!=len(set(ids)):raise ValueError('尾翼id不得重复。')
    if set(ids)&{'main','tail','fuselage','download'}:raise ValueError('尾翼id不能占用main/tail/fuselage/download部件名称。')
    for table in tables:
        a=np.array(table['angle_deg'])
        if np.any(np.diff(a)<=0) or any(len(v)!=len(a) for v in table.values()):
            raise ValueError('机身/尾翼气动表角度必须递增且各列等长。')
        if 'cd' in table and min(table['cd'])<0:raise ValueError('阻力系数不能为负。')


def body_to_ned(roll,pitch):
    sr,cr=np.sin(roll),np.cos(roll);sp,cp=np.sin(pitch),np.cos(pitch)
    return np.array([[cp,sr*sp,cr*sp],[0,cr,-sr],[-sp,sr*cp,cr*cp]])


def flight_velocity(speed,climb,roll,pitch):
    R=body_to_ned(roll,pitch)
    if speed==0:return R.T@np.array([0,0,-climb]),True
    total=np.hypot(speed,climb);a,b=-np.sin(pitch),np.cos(roll)*np.cos(pitch)
    ratio=-climb/(total*np.hypot(a,b));valid=abs(ratio)<=1
    alpha=np.arcsin(np.clip(ratio,-1,1))-np.arctan2(a,b)
    return total*np.array([np.cos(alpha),0,np.sin(alpha)]),valid


def lookup(table,angle,strict):
    if strict and not table['angle_deg'][0]<=angle<=table['angle_deg'][-1]:
        raise ValueError('机身或尾翼攻角/侧滑超出数据域。')
    return {key:float(np.interp(angle,table['angle_deg'],values)) for key,values in table.items() if key!='angle_deg'}


def legacy_wind_loads(fus,v,density,strict=False):
    """Original public dimensional wind-axis tables, converted to SI at import."""
    u,y,w=v;plane=max(float(np.hypot(u,w)),1e-12)
    alpha=np.rad2deg(np.arctan2(w,max(abs(u),1e-12)));beta=np.arctan2(y,plane)
    t=fus['wind_tables'];ca=lookup(t['alpha'],alpha,strict)
    cb=lookup(t['beta'],-np.rad2deg(beta),strict);cc=lookup(t['abs_beta'],abs(np.rad2deg(beta)),strict)
    c,s=u/plane,w/plane;sb,cbeta=np.sin(beta),np.cos(beta)
    T=np.array([[c*cbeta,c*sb,-s],[sb,-cbeta,0],[s*cbeta,s*sb,c]])
    q=.5*density*np.dot(v,v)
    F=T@(-q*np.array([ca['cd_m2']+cc['cd_m2'],cb['cy_m2'],ca['cl_m2']+cb['cl_m2']]))
    M=T@(q*np.array([cb['roll_m3'],-ca['cm_m3']-cc['cm_m3'],cb['yaw_m3']]))
    return F,M,float(alpha),float(np.rad2deg(beta))


def airframe_loads(aircraft,velocity,density,induced_velocity_body,strict=False,body_rates=(0,0,0),tail_induced_velocity_body=(0,0,0)):
    cg=np.asarray(aircraft['mass_properties']['cg_m']);cfg=aircraft['trim'];items={}
    fus=cfg['fuselage'];v=np.asarray(velocity)+fus['wake_fraction']*induced_velocity_body+np.cross(body_rates,np.asarray(fus['position_m'])-cg)
    speed=np.linalg.norm(v);alpha=np.rad2deg(np.arctan2(v[2],v[0])) if speed>1e-9 else 0.
    beta=np.rad2deg(np.arctan2(v[1],np.hypot(v[0],v[2]))) if speed>1e-9 else 0.
    if 'wind_tables' in fus:force,moment,alpha,beta=legacy_wind_loads(fus,v,density,strict)
    else:
        ca,cb=lookup(fus['alpha_table'],alpha,strict),lookup(fus['beta_table'],beta,strict)
        scale=.5*density*speed**2*fus['area_m2'];force=scale*np.array([ca['cx'],cb['cy'],ca['cz']])
        moment=scale*fus['length_m']*np.array([cb['cl'],ca['cm'],cb['cn']])
    moment=moment+np.cross(np.asarray(fus['position_m'])-cg,force)
    items['fuselage']=dict(force_body_n=force.tolist(),moment_cg_body_nm=moment.tolist(),power_w=0,
                           alpha_deg=float(alpha),beta_deg=float(beta))
    for surf in cfg['surfaces']:
        v=(np.asarray(velocity)+surf['wake_fraction']*induced_velocity_body+
           surf.get('tail_wake_fraction',0)*np.asarray(tail_induced_velocity_body)+np.cross(body_rates,np.asarray(surf['position_m'])-cg))
        chord=np.asarray(surf['chord_axis_body']);normal=np.asarray(surf['normal_axis_body'])
        u,w=np.dot(v,chord),np.dot(v,normal);phi=np.arctan2(w,u)
        incidence=surf['incidence_deg']
        if 'incidence_schedule' in surf:
            sched=surf['incidence_schedule'];speed=float(np.linalg.norm(velocity))
            if strict and not sched['speed_m_s'][0]<=speed<=sched['speed_m_s'][-1]:raise ValueError('尾翼安装角调度速度越界。')
            incidence+=np.interp(speed,sched['speed_m_s'],sched['angle_deg'])
        alpha=(incidence-np.rad2deg(phi)+180)%360-180
        query=alpha;reverse=surf.get('reverse_flow_symmetry',False) and abs(alpha)>90
        if reverse:query=np.sign(alpha)*180-alpha
        coeff=lookup(surf['polar'],query,strict)
        if reverse:coeff['cl']=-coeff['cl']
        scale=.5*density*(u*u+w*w)*surf['area_m2']*surf.get('pressure_ratio',1.)
        lift,drag=scale*coeff['cl'],scale*coeff['cd']
        force=(-lift*np.sin(phi)-drag*np.cos(phi))*chord+(lift*np.cos(phi)-drag*np.sin(phi))*normal
        moment=np.cross(np.asarray(surf['position_m'])-cg,force)
        items[surf['id']]=dict(force_body_n=force.tolist(),moment_cg_body_nm=moment.tolist(),power_w=0,alpha_deg=float(alpha),incidence_deg=float(incidence),
                              reverse_flow_estimate=bool(reverse))
    return items
