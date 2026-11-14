"""Four analysis tasks share the current aircraft and persistent case settings."""
from copy import deepcopy
from io import BytesIO
import json
from zipfile import ZipFile,ZIP_DEFLATED
import altair as alt
import pandas as pd
import streamlit as st
from . import designs
from .design_ui import current,edit_table,key_for
from .parameter_fields import label,help_text,location

TASKS={'孤立旋翼':'rotor','整机悬停预算':'hover_budget','整机配平':'trim','通用开环操稳':'open_loop'}


def setting(task,name,title,default,options=None,help=None,**kwargs):
    cfg=current()['settings'].get(task,{})
    value=cfg.get(name,default);key=f'a:{st.session_state["design_epoch"]}:{task}:{name}'
    def changed():current()['settings'].setdefault(task,{})[name]=st.session_state[key]
    common=dict(key=key,on_change=changed,help=help or help_text(name))
    if options is not None:
        return st.selectbox(title,options,index=options.index(value) if value in options else 0,**common,**kwargs)
    if isinstance(default,str):return st.text_input(title,value=value,**common,**kwargs)
    return st.number_input(title,value=value,**common,**kwargs)


def values(text):
    try:return [float(v.strip()) for v in text.replace('，',',').split(',')]
    except ValueError as error:raise ValueError('扫描值请填写用逗号分隔的数值。') from error


def case_controls(task):
    aircraft=current()['aircraft'];main=next(r for r in aircraft['rotors'] if r.get('role','main')=='main')
    batch=None
    if task=='rotor':
        st.caption('选择当前方案中的主旋翼或尾桨，进行固定总距正算、指定拉力反求或批量扫描。桨叶数、几何、气动表及默认转速在详细设置中修改。')
        options=[r['id'] for r in aircraft['rotors']]
        selected=setting(task,'rotor_id','选择分析旋翼',options[0],options,
                         format_func=lambda v:('主旋翼' if v==main['id'] else '尾桨')+' · '+v)
        rotor=next(r for r in aircraft['rotors'] if r['id']==selected)
        mode=setting(task,'mode','旋翼计算方式','固定总距正算',['固定总距正算','指定拉力反求总距','指定拉力反求转速','批量正算','批量反求总距'])
        a,b=st.columns(2)
        with a:speed=setting(task,'axial_speed_m_s','轴向来流 / (m/s)',0.,min_value=0.,max_value=150.)
        with b:density=setting(task,'density_kg_m3','空气密度 / (kg/m³)',1.225,min_value=.05,max_value=3.,format='%.4f')
        st.caption(f"机型默认工况：{rotor['blade_count']}片叶，R={rotor['radius_m']:g} m，{rotor['defaults']['rpm']:g} rpm，总距 {rotor['defaults']['collective_deg']:g}°，径向 {rotor['defaults']['radial_stations']} 站。请在详细设置修改。")
        case=dict(schema_version=2,model='aircraft_rotor',rotor_id=selected,axial_speed_m_s=speed,density_kg_m3=density)
        if '反求' in mode:
            thrust=setting(task,'target_thrust_n','目标拉力 / N',2000.,min_value=.1,max_value=1e7)
            case['target']=dict(thrust_n=thrust,solve_for='rpm' if mode.endswith('转速') else 'collective_deg')
        if '批量' in mode:
            x='target_thrust_n' if '反求' in mode else 'collective_deg'
            text=setting(task,x+'-scan','目标拉力扫描 / N' if x=='target_thrust_n' else '总距扫描 / °','1000,1500,2000' if x=='target_thrust_n' else '8,12,16',help='数值用逗号分隔；失败点会保留诊断。')
            rpm=rotor['defaults']['rpm'];rotor_key='rpm-scan-'+selected
            rpms=setting(task,rotor_key,'转速扫描 / rpm',f'{rpm*.95:g},{rpm:g}',help='数值用逗号分隔。')
            batch=lambda:dict(schema_version=1,kind='rotor_sweep',axes={x:values(text),'rpm':values(rpms)})
        return case,batch
    if aircraft['schema_version']!=2:
        st.info('当前是孤立旋翼模板。请从“200 kg 合成无人直升机”或“UH-60 公开部件模型”新建方案以进行整机分析。')
        return None,None
    st.caption(f"当前整机质量 {aircraft['mass_properties']['mass_kg']:g} kg；重心 {aircraft['mass_properties']['cg_m']} m。质量和重心统一在详细设置修改。")
    case=dict(schema_version=3,model='helicopter',analysis=task)
    if task=='hover_budget':
        mode=setting(task,'mode','预算任务','单点预算',['单点预算','质量—高度图','主桨尺寸—转速图','尾桨尺寸—力臂图','三方案比较'])
        st.caption('功率与载荷预算：闭合垂向力和偏航力矩，同时报告剩余侧力；此任务不标记为六分量配平。')
    elif task=='trim':
        mode=setting(task,'mode','配平任务','单点配平',['单点配平','速度曲线','速度—质量比较','速度—重心比较'])
        st.caption('同一整机方程求解六分量平衡；悬停、正爬升、无侧滑前飞，μ≤0.25且受局部气动表域限制。')
    else:
        mode=setting(task,'mode','开环任务','线化、模态与频响',['线化、模态与频响','小扰动阶跃响应'])
        case['analysis']='linearize' if mode.startswith('线化') else 'response'
        st.caption('低频模型估算：六自由度机体、动态入流、准定常挥舞；叶片变距角输入。完整动态挥舞和惯性耦合仍待补充。')
    a,b,c=st.columns(3)
    with a:case['altitude_m']=setting(task,'altitude_m','飞行高度 / m',0.,min_value=0.,max_value=11000.)
    with b:case['requested_duration_s']=setting(task,'requested_duration_s','需维持时间 / s',600.,min_value=.001,max_value=1e9,help='用于连续或短时功率余量检查，不是响应积分时长。')
    if task!='hover_budget':
        with c:case['speed_m_s']=setting(task,'speed_m_s','水平速度 / (m/s)',0.,min_value=0.,max_value=150.)
        case['climb_m_s']=setting(task,'climb_m_s','爬升率 / (m/s)',0.,min_value=0.,max_value=15.,help='正值向上爬升；下降涡环态尚未覆盖。')
    with st.expander('分析网格与扫描设置'):
        case['radial_stations']=setting(task,'radial_stations','每桨径向叶素数',80,min_value=8,max_value=2000)
        if task!='hover_budget':case['azimuth_stations']=setting(task,'azimuth_stations','整周方位角站数',36,min_value=12,max_value=720,help='对一整周离散；加密用于数值收敛检查。')
        if task=='hover_budget' and '图' in mode:
            tail=next(r for r in aircraft['rotors'] if r['role']=='tail');mass=aircraft['mass_properties']['mass_kg']
            options={'质量—高度图':(('mass_kg','altitude_m'),([mass*.9,mass,mass*1.1],[0,1500,3000])),
                     '主桨尺寸—转速图':(('main_radius_m','main_rpm'),([main['radius_m']*.95,main['radius_m']], [main['defaults']['rpm']*.95,main['defaults']['rpm']])),
                     '尾桨尺寸—力臂图':(('tail_radius_m','tail_arm_m'),([tail['radius_m']*.95,tail['radius_m']], [abs(tail['position_m'][0]-aircraft['mass_properties']['cg_m'][0])]))}
            keys,defaults=options[mode]
            from .presentation import AXIS_LABELS
            strings=[setting(task,k+'-scan',AXIS_LABELS[k]+'（逗号分隔）',','.join(f'{v:g}' for v in vals)) for k,vals in zip(keys,defaults)]
            batch=lambda:dict(schema_version=1,kind='helicopter_sweep',axes={k:values(s) for k,s in zip(keys,strings)})
        elif task=='hover_budget' and mode=='三方案比较':
            cfg=current()['settings'].setdefault(task,{})
            rows=cfg.setdefault('variants',[dict(name=n,mass_kg=aircraft['mass_properties']['mass_kg']*f,
                main_radius_m=main['radius_m'],main_rpm=main['defaults']['rpm']) for n,f in [('基准方案',1.),('轻载方案',.9),('重载方案',1.1)]])
            def apply(rows):cfg['variants']=rows
            edit_table(rows,['settings',task,'variants'],apply,dynamic=True,columns={
                'name':st.column_config.TextColumn('候选方案名称'),
                'mass_kg':st.column_config.NumberColumn('整机质量 / kg'),
                'main_radius_m':st.column_config.NumberColumn('主桨半径 / m'),
                'main_rpm':st.column_config.NumberColumn('主桨转速 / rpm')})
            batch=lambda:dict(schema_version=1,kind='helicopter_comparison',variants=[dict(name=r['name'],overrides={k:v for k,v in r.items() if k!='name'}) for r in cfg['variants']])
        elif task=='trim' and mode!='单点配平':
            speed=setting(task,'speed-scan','速度扫描 / (m/s)','0,5,10,15,20')
            group=None
            if mode=='速度—质量比较':group='mass_kg';default=str(aircraft['mass_properties']['mass_kg'])
            if mode=='速度—重心比较':group='cg_x_m';default=str(aircraft['mass_properties']['cg_m'][0])
            groups=setting(task,group+'-scan','质量扫描 / kg' if group=='mass_kg' else '重心 x 扫描 / m',default) if group else None
            batch=lambda:dict(schema_version=1,kind='helicopter_trim_sweep',axes={'speed_m_s':values(speed),**({group:values(groups)} if group else {})},continuation=True)
        if case['analysis']=='response':
            from .presentation import CONTROL_LABELS
            case['control']=setting(task,'control','阶跃操纵','main_collective',list(CONTROL_LABELS),format_func=lambda v:CONTROL_LABELS[v])
            case['amplitude_deg']=setting(task,'amplitude_deg','阶跃幅值 / °',.05,min_value=-2.,max_value=2.,format='%.3f')
            case['duration_s']=setting(task,'duration_s','响应时长 / s',.1,min_value=.01,max_value=10.)
            case['time_step_s']=setting(task,'time_step_s','响应时间步 / s',.001,options=[.01,.005,.002,.001,.0005])
    return case,batch


def input_rows(design):
    rows=[]
    def walk(value,path):
        if isinstance(value,dict):
            for key,v in value.items():
                if key not in ('schema_version','kind','units','axes'):walk(v,path+[key])
        elif isinstance(value,list) and len(value)>6:rows.append({'参数':location(path),'本次输入':f'{len(value)}个节点（完整数据在方案包）'})
        elif isinstance(value,list) and value and isinstance(value[0],dict):
            for i,v in enumerate(value):walk(v,path+[i])
        else:rows.append({'参数':location(path),'本次输入':str(value)})
    walk(design['aircraft'],[]);return rows


def input_fingerprint(design,case,batch):
    return designs.digest(dict(aircraft=design['aircraft'],assets=design['assets'],case=case,batch=batch))


def show_result(record,is_current):
    answer,files=record['answer'],record['files']
    if not is_current:st.warning('参数或工况已修改；以下仍是上次运行结果，点击运行后才会更新。')
    st.subheader('计算结果 · '+record['design']['aircraft']['name'])
    with st.expander('本次实际输入与来源'):
        st.dataframe(pd.DataFrame(input_rows(record['design'])),hide_index=True)
        st.write('本次工况',record['case'])
        edits=record['design']['settings'].get('_edits',[])
        if edits:st.caption('已修改字段：'+'；'.join(edits))
    if answer['status']!='converged':st.error(answer.get('error','未得到有效结果，请根据诊断修改参数后重跑。'))
    summary=answer.get('summary') or {}
    specs=[('thrust_n','拉力','N',1),('torque_nm','轴扭矩','N·m',1),('power_w','轴功率','kW',.001),
           ('required_power_w','整机需用轴功率','kW',.001),('duration_margin_w','功率余量','kW',.001),
           ('tail_thrust_n','尾桨推力','N',1),('states','动态状态数','',1),('unstable_modes','不稳定特征根数','',1)]
    chosen=[v for v in specs if v[0] in summary]
    if chosen:
        cols=st.columns(min(3,len(chosen)))
        for i,(key,title,unit,factor) in enumerate(chosen):cols[i%len(cols)].metric(title,f'{summary[key]*factor:.5g} {unit}')
    if 'total' in summary:st.write('批量统计',summary)
    if answer.get('feasible') is False:
        st.warning('当前方案未满足所给设计限制。请结合求解状态，查看功率、操纵余量和专业诊断。')
    states={'converged':'已收敛','failed':'失败','partial':'部分完成','within_budget_input_domain':'在预算适用范围内',
            'within_domain':'在数据域内','within_input_domain':'在输入范围内','supported':'在支持范围内',
            'exceeded':'超出给定限制','satisfied':'满足给定限制','within_supplied_limits':'满足给定限制',
            'not_established':'尚未确定','not_converged':'未收敛','trim_failed':'基点配平失败',
            'within_implemented_steady_domain':'在当前稳态模型范围内','within_implemented_reduced_domain':'在当前低频模型范围内',
            'outside_implemented_domain':'超出当前模型范围','outside_implemented_reduced_domain':'超出当前低频模型范围',
            'derivative_step_sensitive':'导数对差分步长敏感','response_stopped':'响应积分已停止',
            'not_evaluated':'未检查','unknown':'待检查'}
    text=lambda value:states.get(str(value),str(value))
    st.caption('求解：'+text(answer.get('solver_status',answer['status']))+'；数据域：'+text(answer.get('support_status','见诊断'))+'；设计限制：'+text(answer.get('design_limits_status','见诊断')))
    for name in ('performance.png','controls.png','modes.png','frequency.png','response.png'):
        if name in files:st.image(files[name])
    if 'radial_loads.csv' in files:
        data=pd.read_csv(BytesIO(files['radial_loads.csv']))
        for key,title in [('thrust_n_per_m','单位展长拉力 / (N/m)'),('torque_nm_per_m','单位展长扭矩 / (N·m/m)')]:
            chart=alt.Chart(data).mark_line().encode(x=alt.X('r_m',title='半径 / m'),y=alt.Y(key,title=title))
            st.altair_chart(chart,width='stretch')
    for name in ('trim.csv','budget.csv','performance.csv','modes.csv'):
        if name in files:
            with st.expander('结果表：'+{'trim.csv':'配平','budget.csv':'功率收支','performance.csv':'批量性能','modes.csv':'模态'}[name]):
                st.dataframe(pd.read_csv(BytesIO(files[name])),hide_index=True)
    for warning in answer.get('warnings',[]):st.caption(warning)
    with st.expander('专业诊断与操纵余量'):st.json({k:v for k,v in answer.items() if k not in ('summary','warnings')})
    archive=BytesIO()
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    st.download_button('下载本次结果、方案与复算工况',archive.getvalue(),'rotordesignlab-result.zip',key='download-result')


def render(task_label):
    task=TASKS[task_label]
    base_errors=designs.issues(current())
    if base_errors:
        st.warning('请先修正详细设置中的参数：')
        for error in base_errors:st.error(error)
        return
    case,batch=case_controls(task)
    if case is None:return
    if st.button('检查当前方案参数'):
        errors=designs.issues(current(),case.get('analysis'))
        if errors:
            for error in errors:st.error(error)
        else:st.success('当前分析所需的机型和数据表检查通过；实际工况的数据域在求解时继续检查。')
    if st.button('运行分析',type='primary'):
        st.session_state.pop('workspace-result',None)
        try:
            submitted=deepcopy(current());spec=batch() if batch else None
            with st.spinner('计算中，请等待结果…'):answer,files=designs.execute(submitted,case,spec)
            st.session_state['workspace-result']=dict(answer=answer,files=files,design=submitted,
                 fingerprint=designs.digest(submitted),input_fingerprint=input_fingerprint(submitted,case,spec),case=deepcopy(case),task=task)
        except (ValueError,OSError,KeyError,TypeError) as e:st.error(str(e))
    record=st.session_state.get('workspace-result')
    if record and record['task']==task:
        try:same=record['input_fingerprint']==input_fingerprint(current(),case,batch() if batch else None)
        except (ValueError,KeyError,TypeError):same=False
        show_result(record,same)
