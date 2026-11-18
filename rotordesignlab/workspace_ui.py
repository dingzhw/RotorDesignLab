"""Four analysis tasks share the current aircraft and persistent case settings."""
from copy import deepcopy
from io import BytesIO
import json
from zipfile import ZipFile,ZIP_DEFLATED
import altair as alt
import pandas as pd
import streamlit as st
from . import designs
from .design_ui import current,edit_table,key_for,details
from .parameter_fields import label,help_text,location
from .model_scope import OPEN_LOOP_LABEL, SPATIAL_SCOPE, RESPONSE_DURATION_BOUNDS

TASKS={'孤立旋翼':'rotor','整机悬停预算':'hover_budget','整机配平':'trim',OPEN_LOOP_LABEL:'open_loop'}
from .comparison_ui import LABEL as DESIGN_COMPARISON


def setting(task,name,title,default,options=None,help=None,**kwargs):
    cfg=current()['settings'].get(task,{})
    value = cfg.get(name, default)
    key = f'a:{st.session_state["design_epoch"]}:{task}:{name}'
    def changed():
        current()['settings'].setdefault(task, {})[name] = st.session_state[key]
        if task == 'rotor' and name == 'flow_model':
            from .design_models import stamp
            from . import __version__
            stamp(current()['settings'], __version__)
    common=dict(key=key,on_change=changed,help=help or help_text(name))
    if options is not None:
        return st.selectbox(title,options,index=options.index(value) if value in options else 0,**common,**kwargs)
    if isinstance(default, str):
        return st.text_input(title, value=value, **common, **kwargs)
    if isinstance(value, (int, float)):
        for bound, invalid in (('min_value', lambda v, limit: v < limit), ('max_value', lambda v, limit: v > limit)):
            if bound in kwargs and invalid(value, kwargs[bound]):
                st.error(f'{title}保存值{value:g}超出允许边界{kwargs[bound]:g}；已保留原值，请在此修改。')
                kwargs[bound] = value
    # Converted velocity widgets already have an explicit value in session state.
    # A second widget default would compete with that value on a view switch.
    initial = None if key in st.session_state else value
    return st.number_input(title, value=initial, **common, **kwargs)


def values(text):
    try:return [float(v.strip()) for v in text.replace('，',',').split(',')]
    except ValueError as error:raise ValueError('扫描值请填写用逗号分隔的数值。') from error


def case_controls(task, hover=False):
    def task_setting(task, *args, **kwargs):
        return setting("hover_trim" if hover else task, *args, **kwargs)
    aircraft=current()['aircraft'];main=next(r for r in aircraft['rotors'] if r.get('role','main')=='main')
    batch=None
    if task=='rotor':
        st.subheader('孤立旋翼计算工况')
        st.caption('直接填写本次总距、转速和来流，再点击运行。桨叶几何、安装和气动表在下方详细设置中修改。')
        options=[r['id'] for r in aircraft['rotors']]
        selected=task_setting(task,'rotor_id','选择分析旋翼',options[0],options,
                         format_func=lambda v:('主旋翼' if v==main['id'] else '尾桨')+' · '+v)
        rotor=next(r for r in aircraft['rotors'] if r['id']==selected)
        mode=task_setting(task,'mode','旋翼计算方式','固定总距正算',['固定总距正算','指定拉力反求总距','指定拉力反求转速','批量正算','批量反求总距'],help='正算：给总距与转速求拉力；反求：给目标拉力求总距或转速；批量：按扫描值逐点计算。')
        from .design_models import rotor_model, AXIAL, SPATIAL
        resolved = rotor_model(current()['settings'])
        pending = '请选择原方案使用的模型'
        choices = [SPATIAL, AXIAL] if resolved else [pending, AXIAL, SPATIAL]
        if resolved is None:
            st.warning('此历史方案未保存求解模型，修订号不足以判断。请依据原计算记录选择轴流或三方向模型；选择前不会启动计算。原方案文件保持不变。')
        flow_model=task_setting(task,'flow_model','来流与旋翼模型',resolved or pending,
             choices,
             help='三方向模型按方位角分解相对速度，支持盘面内来流与周期变距。轴流模型保留原悬停/轴流验证口径，两者的入流分布和挥舞假设不同。')
        if flow_model == pending:
            return None, None
        spatial=flow_model.startswith('三方向')
        a,b=st.columns(2)
        with a:rpm=task_setting(task,'rpm-'+selected,'本次旋翼转速 / rpm',float(rotor['defaults']['rpm']),
                           min_value=1.,max_value=30000.,disabled=mode=='指定拉力反求转速',help=help_text('rpm'))
        with b:collective=task_setting(task,'collective-'+selected,'本次总距 θ₀ / °',float(rotor['defaults']['collective_deg']),
                                  min_value=-20.,max_value=55.,disabled='反求总距' in mode,
                                  help='总距参考站的桨距角，增加为正；参考站在下方桨叶参数中设置。反求总距时，本项作为初始参考，结果给出求得总距。')
        if spatial:
            st.caption(SPATIAL_SCOPE)
            from .velocity_ui import render_velocity, inflow_preview
            velocity_input = render_velocity(current(), st.session_state['design_epoch'], task_setting)
        else:
            speed=task_setting(task,'axial_speed_m_s','轴向来流 / (m/s)',0.,min_value=0.,max_value=150.)
        from .environment_ui import render_environment
        environment = render_environment(current(), task, task_setting, rotor=rotor)
        st.caption(f"当前旋翼：{rotor['blade_count']}片桨叶，R={rotor['radius_m']:g} m；总距参考站 r/R={rotor['pitch_reference_r_over_R']:g}。本页工况随方案保存，优先于机型参考工况。")
        case=dict(schema_version=2,model='spatial_rotor' if spatial else 'aircraft_rotor',rotor_id=selected,
                  rpm=rpm,collective_deg=collective, **environment)
        if spatial:
            case.update(velocity_input)
            inflow_preview(case, rotor, rpm)
        else:
            case['axial_speed_m_s'] = speed
        with st.expander('周期变距、挥舞与计算网格'):
            case['radial_stations']=task_setting(task,'radial-'+selected,'本次径向叶素数',rotor['defaults']['radial_stations'],min_value=8,max_value=2000,help=help_text('radial_stations'))
            if spatial:
                a,b=st.columns(2)
                for col,key,symbol in ((a,'cyclic_cos_deg','cos'),(b,'cyclic_sin_deg','sin')):
                    with col:case[key]=task_setting(task,key+'-'+selected,symbol+' 周期变距 / °',0.,min_value=-30.,max_value=30.,
                        help=help_text('cyclic_cos_deg'))
                choices=['fixed','aircraft'] if 'flight' in rotor else ['fixed']
                case['flapping_model']=task_setting(task,'flapping-'+selected,'桨叶运动模型','fixed',choices,
                    format_func=lambda v:{'fixed':'固定桨叶（保留预锥）','aircraft':'使用机型挥舞参数'}[v],
                    help='固定桨叶不求挥舞平衡；使用机型参数时求解锥度和一阶挥舞，需提供相应惯量、质量一阶矩及铰接参数。')
                case['azimuth_stations']=task_setting(task,'azimuth_stations','整周方位角站数',36,min_value=12,max_value=720)
                st.caption('三状态入流；μ≤0.25、正推力和正轴功率，并受当地攻角/Mach/Re数据域限制。当前不含下降涡环态、展向气动力和非定常失速。')
        if spatial:
            with st.expander('方位、旋向与本次周期变距图'):
                from .coordinates import canonical_spatial_case
                from .mounting import azimuth_figure, coordinate_metadata
                from matplotlib import pyplot as plt
                try:
                    flow = canonical_spatial_case(case)['flow_body_m_s']
                    fig = azimuth_figure(rotor, flow, [collective, case['cyclic_cos_deg'], case['cyclic_sin_deg']])
                    st.pyplot(fig)
                    plt.close(fig)
                    metadata = coordinate_metadata(rotor)
                    st.caption(f"实际ψ=0°方向（机体系）：{metadata['x_zero_body']}；图中机体方向为在当前桨盘上的投影。")
                    st.caption('新主桨模板取机尾零方位，旧方案按原值。cos/sin是此实际方位下的谐波系数，不是未经杆系映射的驾驶杆方向。')
                except (ValueError, TypeError, KeyError) as error:
                    st.warning('暂不能显示方位图：' + str(error))
        if '反求' in mode:
            thrust=task_setting(task,'target_thrust_n','目标拉力 / N',2000.,min_value=.1,max_value=1e7)
            case['target']=dict(thrust_n=thrust,solve_for='rpm' if mode.endswith('转速') else 'collective_deg')
        if '批量' in mode:
            x='target_thrust_n' if '反求' in mode else 'collective_deg'
            if spatial and x=='collective_deg':
                from .coordinates import FLOW_AXES, MOTION_AXES
                from .presentation import AXIS_LABELS
                x = setting(task, 'sweep_variable', '扫描变量', 'collective_deg', ['collective_deg', *MOTION_AXES, *FLOW_AXES],
                            format_func=lambda value: AXIS_LABELS[value],
                            help='扫描轴按其名称所指的参考系定义，独立于当前输入视角；同参考系其他分量保持不变，第二变量为转速。')
            from .presentation import AXIS_LABELS
            default = ('1000,1500,2000' if x == 'target_thrust_n' else '8,12,16' if x == 'collective_deg'
                       else '0,5,10' if x == 'flow_z_m_s' else '0,10,20' if x.startswith('motion_') else '0,-10,-20')
            title=('目标拉力扫描 / N' if x=='target_thrust_n' else '总距扫描 / °' if x=='collective_deg' else AXIS_LABELS[x]+'（扫描值）')
            text=task_setting(task,x+'-scan',title,default,help='数值用逗号分隔；失败点会保留诊断。')
            rpm=rotor['defaults']['rpm'];rotor_key='rpm-scan-'+selected
            rpms=task_setting(task,rotor_key,'转速扫描 / rpm',f'{rpm*.95:g},{rpm:g}',help='数值用逗号分隔。')
            batch=lambda:dict(schema_version=1,kind='rotor_sweep',axes={x:values(text),'rpm':values(rpms)})
        return case,batch
    if aircraft['schema_version']!=2:
        st.info('当前是孤立旋翼模板。请从“200 kg 合成无人直升机”或“UH-60 公开部件模型”新建方案以进行整机分析。')
        return None,None
    st.caption(f"当前整机质量 {aircraft['mass_properties']['mass_kg']:g} kg；重心 {aircraft['mass_properties']['cg_m']} m。质量和重心在整机装配的详细设置中统一修改。")
    case=dict(schema_version=3,model='helicopter',analysis=task)
    if task=='hover_budget':
        mode=task_setting(task,'mode','预算任务','单点预算',['单点预算','预算—配平功率对照',DESIGN_COMPARISON,'质量—高度图','主桨尺寸—转速图','尾桨尺寸—力臂图','三方案比较'],help='方法对照比较同装配的两种模型；同任务三方案用同一配平模型比较设计参数；原三方案比较仍为预算变体。')
        if mode == DESIGN_COMPARISON:
            case.update(analysis='trim', speed_m_s=0., climb_m_s=0.)
        if mode == '预算—配平功率对照':
            case['analysis'] = 'hover_comparison'
        st.caption('三方案分别求六分量悬停配平，同时报告动力与操纵余量。' if mode == DESIGN_COMPARISON else
                   '功率与载荷预算：闭合垂向力和偏航力矩，同时报告剩余侧力；此任务不标记为六分量配平。')
    elif task=='trim':
        mode = '单点配平' if hover else task_setting(task,'mode','配平任务','单点配平',['单点配平',DESIGN_COMPARISON,'速度曲线','速度—质量比较','速度—重心比较'],help='同任务三方案共用速度、环境和持续时间，比较设计参数；扫描保留原语义。')
        st.caption('同一整机方程求解六分量平衡；悬停、正爬升、无侧滑前飞，μ≤0.25且受局部气动表域限制。')
    else:
        mode = setting(task, 'mode', '开环任务', '线化、模态与频响',
                       ['线化、模态与频响', '小扰动阶跃响应'],
                       format_func=lambda value: '小扰动响应' if value == '小扰动阶跃响应' else value,
                       help='先配平，再计算矩阵/频响或响应。响应可选平滑脉冲、正负双脉冲和阶跃；使用当前重心惯量。')
        case['analysis']='linearize' if mode.startswith('线化') else 'response'
        from .model_scope import open_loop_restriction
        restriction = open_loop_restriction(aircraft)
        if restriction['issue']:
            st.warning(restriction['note'])
            acknowledged = st.checkbox('仅作故障诊断，查看矩阵与响应', value=False,
                                        key=f'diagnostic:{st.session_state["design_epoch"]}',
                                        help='允许计算和导出诊断数据，不恢复工程评价资格。')
            if not acknowledged:
                return None, None
            case['diagnostic_only'] = True
        st.caption('低频模型估算：六自由度机体、动态入流、准定常挥舞；桨叶变距角输入。完整动态挥舞和惯性耦合仍待补充。')
    from .download import settings as download_settings
    download = download_settings(aircraft, case['analysis'])
    if case['analysis'] == 'hover_comparison':
        st.caption(f"预算下载比例：{aircraft['hover']['download_fraction']:.1%}；六分量配平比例：{download['effective_fraction']:.1%}。")
    else:
        st.caption(f"本次附加下载比例：{download['effective_fraction']:.1%}。" + download['note'])
    st.caption(download['comparison_note'])
    a,b,c=st.columns(3)
    with a:case['altitude_m']=task_setting(task,'altitude_m','飞行高度 / m',0.,min_value=0.,max_value=11000.)
    with b:case['requested_duration_s']=task_setting(task,'requested_duration_s','需维持时间 / s',600.,min_value=.001,max_value=1e9,help='用于连续或短时功率余量检查，不是响应积分时长。')
    from .environment_ui import render_environment
    case.update(render_environment(current(), task, task_setting, altitude=case['altitude_m']))
    if task!='hover_budget':
        if hover:
            case.update(speed_m_s=0., climb_m_s=0.)
            st.caption('悬停六分量配平：水平速度=0、爬升率=0；与前飞配平使用同一方程，工况独立保存。')
        else:
            with c:
                case['speed_m_s'] = task_setting(task,'speed_m_s','水平速度 / (m/s)',0.,min_value=0.,max_value=150.)
            case['climb_m_s'] = task_setting(task,'climb_m_s','爬升率 / (m/s)',0.,min_value=0.,max_value=15.,help='正值向上爬升；下降涡环态尚未覆盖。')
    with st.expander('分析网格与扫描设置'):
        case['radial_stations']=task_setting(task,'radial_stations','每桨径向叶素数',80,min_value=8,max_value=2000)
        if task != 'hover_budget' or case['analysis'] in ('hover_comparison', 'trim'):
            case['azimuth_stations'] = task_setting(task, 'azimuth_stations', '整周方位角站数', 36,
                min_value=12, max_value=720, help='六分量配平采用的方位离散；轴流预算只使用径向网格。')
        if mode == DESIGN_COMPARISON:
            st.caption('候选方案在下方逐项设置；三方案采用相同分析网格。')
        elif task=='hover_budget' and '图' in mode:
            tail=next(r for r in aircraft['rotors'] if r['role']=='tail');mass=aircraft['mass_properties']['mass_kg']
            options={'质量—高度图':(('mass_kg','altitude_m'),([mass*.9,mass,mass*1.1],[0,1500,3000])),
                     '主桨尺寸—转速图':(('main_radius_m','main_rpm'),([main['radius_m']*.95,main['radius_m']], [main['defaults']['rpm']*.95,main['defaults']['rpm']])),
                     '尾桨尺寸—力臂图':(('tail_radius_m','tail_arm_m'),([tail['radius_m']*.95,tail['radius_m']], [abs(tail['position_m'][0]-aircraft['mass_properties']['cg_m'][0])]))}
            keys,defaults=options[mode]
            from .presentation import AXIS_LABELS
            strings=[setting(task,k+'-scan',AXIS_LABELS[k]+'（逗号分隔）',','.join(f'{v:g}' for v in vals),help='按表头单位输入多个数值，用逗号分隔。各参数组合逐点计算，失败点保留原因。') for k,vals in zip(keys,defaults)]
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
            speed=task_setting(task,'speed-scan','速度扫描 / (m/s)','0,5,10,15,20',help='填写水平速度列表，用逗号分隔；从低速到高速可使用相邻工况续接。')
            group=None
            if mode=='速度—质量比较':group='mass_kg';default=str(aircraft['mass_properties']['mass_kg'])
            if mode=='速度—重心比较':group='cg_x_m';default=str(aircraft['mass_properties']['cg_m'][0])
            groups=task_setting(task,group+'-scan','质量扫描 / kg' if group=='mass_kg' else '重心 x 扫描 / m',default,help='用逗号分隔候选值。质量单位kg；重心x相对机型原点、向前为正。') if group else None
            batch=lambda:dict(schema_version=1,kind='helicopter_trim_sweep',axes={'speed_m_s':values(speed),**({group:values(groups)} if group else {})},continuation=True)
    if mode == DESIGN_COMPARISON:
        from .comparison_ui import candidate_form
        batch = candidate_form(aircraft, setting, 'design-comparison')
    if case['analysis'] == 'response':
        from .presentation import CONTROL_LABELS
        modern = current()['settings'].get('_workspace_revision', 3) >= 4
        st.subheader('扰动输入与观察窗口')
        case['control'] = setting(task, 'control', '扰动操纵', 'main_collective', list(CONTROL_LABELS),
                                  format_func=lambda value: CONTROL_LABELS[value],
                                  help='给所选桨叶变距角叠加小扰动；其余操纵保持配平值。')
        names = {'pulse': '平滑脉冲（sin²）', 'doublet': '正负双脉冲', 'step': '阶跃'}
        case['input_type'] = setting(task, 'input_type', '扰动波形', 'pulse' if modern else 'step', list(names),
                                     format_func=lambda value: names[value],
                                     help='平滑脉冲在一段持续时间后归零；双脉冲先正后负，各持续一段；阶跃开始后一直保持。')
        case['amplitude_deg'] = setting(task, 'amplitude_deg', '扰动峰值 / °', .05, min_value=-2., max_value=2.,
                                        format='%.3f', help='相对配平操纵的角度增量。负峰值反转波形符号，建议从0.05°开始。')
        case['duration_s'] = setting(task, 'duration_s', '响应时长 / s', 2. if modern else .1,
                                     min_value=RESPONSE_DURATION_BOUNDS[0], max_value=RESPONSE_DURATION_BOUNDS[1],
                                     help='完整观察窗口，与扰动持续时间分开；开环不稳定响应可能增长或越界中止。')
        case['input_start_s'] = setting(task, 'input_start_s', '扰动开始时间 / s', .2 if modern else 0.,
                                        min_value=0., max_value=10., help='从配平状态开始计时；此时刻之前不施加扰动。')
        if case['input_type'] != 'step':
            case['input_duration_s'] = setting(task, 'input_duration_s', '每段扰动持续时间 / s', .5,
                                               min_value=.001, max_value=10.,
                                               help='平滑脉冲为总持续时间；双脉冲每段均取此值，总持续时间为两倍。')
        case['time_step_s'] = setting(task, 'time_step_s', '响应时间步 / s', .001,
                                      options=[.01, .005, .002, .001, .0005],
                                      help='需满足最快模型模态的步长限制；程序在输入跳变处自动拆步，观察窗口须为此步长整数倍。')
        st.caption('响应逐步重算旋翼载荷，耗时明显长于线化；可先缩短观察窗口检查输入。')
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
    if case.get('model') == 'spatial_rotor':
        from .coordinates import canonical_spatial_case
        case = canonical_spatial_case(case)
        # Ignore only round-off from a view round trip, not physical input edits.
        case['flow_body_m_s'] = [0. if abs(v) < 5e-13 else round(v, 12) for v in case['flow_body_m_s']]
        case.setdefault('attitude_deg', [0., 0.])
    content = dict(aircraft=design['aircraft'], assets=design['assets'], case=case, batch=batch)
    if design.get('format_version') == 2:
        content['assembly'] = design['assembly']
    return designs.digest(content)


def show_result(record,is_current):
    answer,files=record['answer'],record['files']
    from .model_scope import open_loop_restriction
    restriction = answer.get('evaluation_restriction')
    if record.get('task') == 'open_loop' and restriction is None:
        restriction = open_loop_restriction(record['design']['aircraft'])
    if restriction:
        st.warning(restriction['note'])
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
           ('collective_deg','计算总距','°',1),('rpm','计算转速','rpm',1),
           ('required_power_w','整机需用轴功率','kW',.001),('duration_margin_w','功率余量','kW',.001),
           ('tail_thrust_n','尾桨推力','N',1),('states','动态状态数','',1),('unstable_modes','不稳定特征根数','',1)]
    chosen=[v for v in specs if v[0] in summary and not (restriction and v[0] == 'unstable_modes')]
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
            'not_evaluated':'未检查','unknown':'待检查','per_point':'见逐点状态','per_method':'见两种方法各自状态'}
    text=lambda value:states.get(str(value),str(value))
    st.caption('求解：'+text(answer.get('solver_status',answer['status']))+'；数据域：'+text(answer.get('support_status','见诊断'))+'；设计限制：'+text(answer.get('design_limits_status','见诊断'))+'；验证依据：'+{'model_estimate':'模型估算'}.get(answer.get('evidence_status'), '见逐项验证记录'))
    if answer.get('model_maturity'):
        st.info(answer['model_maturity'])
    if 'design-comparison.csv' in files:
        table = pd.read_csv(BytesIO(files['design-comparison.csv']))
        st.subheader('同任务三方案 · 功率与裕度')
        columns = [c for c in table.columns if c in ('方案','求解','支持范围','设计限制','验证依据','失败原因') or c.endswith('_kW')]
        st.dataframe(table[columns], hide_index=True)
        with st.expander('关键设计参数、配平与双向操纵余量', expanded=True):
            st.dataframe(table[[c for c in table.columns if c == '方案' or c not in columns]], hide_index=True)
        st.download_button('下载三方案中文对照表', table.to_csv(index=False).encode('utf-8-sig'), '同任务三方案.csv')
        for entry in answer.get('candidates', []):
            with st.expander(entry['name']+'：来源、假设与诊断'):
                st.write(entry['change']['provenance'])
                for key, source in entry.get('sources', {}).items():
                    title = {'aircraft':'原装配来源', 'mass_properties':'质量惯量来源',
                             'rotors':'旋翼来源', 'powerplant':'动力来源'}[key]
                    st.write(title+'：'+str(source))
                st.caption(entry['geometry_rule']+'；'+entry['mass_inertia_update'])
                if entry['result'].get('error'):
                    st.error(entry['result']['error'])
                for warning in entry['result'].get('warnings', []):
                    st.caption(warning)
        if 'report.md' in files:
            st.download_button('下载三方案分析摘要', files['report.md'], '同任务三方案.md')
    if 'power-comparison.csv' in files:
        if answer.get('power_feasibility_depends_on_method'):
            st.warning('功率可行性依赖模型假设：预算与配平给出不同判定，请查看分项和所用假设。')
        st.dataframe(pd.read_csv(BytesIO(files['power-comparison.csv'])), hide_index=True)
        st.download_button('下载功率方法对照表', files['power-comparison.csv'], '功率方法对照.csv')
    for method, item in answer.get('methods', {}).items():
        title = '悬停预算' if method == 'hover_budget' else '六分量配平'
        st.caption(title+'：求解 '+text(item.get('solver_status', item['status']))+
                   '；数据域 '+text(item.get('support_status', 'unknown'))+
                   '；设计限制 '+text(item.get('design_limits_status', 'not_evaluated'))+'；依据：模型估算。')
        if item['status'] != 'converged':
            st.caption(item.get('error', '计算失败，详见该方法诊断。'))
        if 'power_accounting' in item:
            show_power_accounting(item['power_accounting'], title)
    if 'power_accounting' in answer:
        show_power_accounting(answer['power_accounting'], '本次计算')
    if answer.get('download_model'):
        download = answer['download_model']
        st.caption(f"实际附加下载比例：{download['effective_fraction']:.1%}。" + download['note'])
        st.caption(download['comparison_note'])
    installation=answer.get('installation',{})
    if 'moment_hub_body_nm' in installation:
        st.caption('整转平均气动力：机体系X向前、Y向右、Z向下；力矩按右手定则。桨毂力矩与移轴到重心的力矩分别列出。')
        st.dataframe(pd.DataFrame([
            {'载荷':'气动力 / N',**dict(zip(('X','Y','Z'),installation['force_body_n']))},
            {'载荷':'关于桨毂的气动力矩 / (N·m)',**dict(zip(('X','Y','Z'),installation['moment_hub_body_nm']))},
            {'载荷':'关于重心的气动力矩 / (N·m)',**dict(zip(('X','Y','Z'),installation['moment_cg_body_nm']))},
        ]),hide_index=True)
    for name in ('performance.png','azimuth.png','controls.png','modes.png','frequency.png','input.png','response.png'):
        if name in files:st.image(files[name])
    if 'radial_loads.csv' in files:
        data=pd.read_csv(BytesIO(files['radial_loads.csv']))
        for key,title in [('thrust_n_per_m','单位展长拉力 / (N/m)'),('torque_nm_per_m','单位展长扭矩 / (N·m/m)')]:
            chart=alt.Chart(data).mark_line().encode(x=alt.X('r_m',title='半径 / m'),y=alt.Y(key,title=title))
            st.altair_chart(chart,width='stretch')
    for name in ('trim.csv','budget.csv','performance.csv','modes.csv'):
        if name in files:
            with st.expander('结果表：'+{'trim.csv':'配平','budget.csv':'功率收支','performance.csv':'批量性能','modes.csv':'模态'}[name]):
                from .engineering_display import result_table
                table = result_table(pd.read_csv(BytesIO(files[name])))
                st.dataframe(table, hide_index=True)
                st.download_button('下载中文结果表', table.to_csv(index=False).encode('utf-8-sig'),
                                   '中文-' + name, key='zh-' + name)
    for warning in answer.get('warnings',[]):st.caption(warning)
    with st.expander('专业诊断与操纵余量'):
        from .engineering_display import label as engineering_label, result_table
        statuses = {engineering_label(k): engineering_label(answer.get(k, 'not_evaluated')) for k in
                    ('solver_status', 'support_status', 'design_limits_status', 'evidence_status')}
        st.write(statuses)
        margins = answer.get('control_margins_deg', answer.get('control_margins', {}))
        if margins:
            st.dataframe(result_table(pd.DataFrame(margins).T.reset_index(names='操纵量')), hide_index=True)
        if 'error' in answer:
            st.error(answer['error'])
        with st.expander('原始字段与完整诊断（供复算核查）'):
            st.json({k: v for k, v in answer.items() if k not in ('summary', 'warnings')})
    archive=BytesIO()
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    st.download_button('下载本次结果、方案与复算工况',archive.getvalue(),'rotordesignlab-result.zip',key='download-result')


def show_power_accounting(accounting, title):
    with st.expander(title+'：功率分账与模型假设'):
        rows = []
        inflow = {'uniform': '均匀轴流', 'annular': '环带轴流', 'steady_pitt_peters': '稳态三状态入流'}
        for item in accounting['components']:
            rows.append({'部件': '主桨' if item['role'] == 'main' else '尾桨',
                         '气动轴功率_kW': item['shaft_power_w']/1000, '传动效率': item['efficiency'],
                         '传动损失_kW': item['loss_w']/1000, '入流': inflow[item['inflow']],
                         '尖损失': 'Prandtl' if item['tip_loss'] == 'prandtl' else '不附加',
                         '桨叶运动': {'fixed_axial': '轴流固定', 'fixed': '固定', 'hinged': '铰接挥舞'}[item['flap']],
                         '预锥角_deg': item['precone_deg'],
                         '计算挥舞[锥度,cos,sin]_deg': str(item['solved_flap_deg']) if item['solved_flap_deg'] is not None else '固定预锥',
                         '偏航推力臂_m': item['yaw_thrust_arm_m']})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        rating = '短时' if accounting['rating'] == 'short_time' else '连续'
        st.caption(f"附件 {accounting['accessory_power_w']/1000:.4g} kW；持续 {accounting['requested_duration_s']:g} s，"
                   f"采用{rating}可用功率 {accounting['selected_available_w']/1000:.4g} kW。")
        st.caption(f"连续可用 {accounting['continuous_available_w']/1000:.4g} kW；短时可用 "
                   f"{accounting['short_time_available_w']/1000:.4g} kW，限时 {accounting['short_time_duration_s']:g} s。")
        st.caption(f"实际附加下载比例 {accounting['download']['effective_fraction']:.1%}；"
                   '下载力[X,Y,Z] / N：'+str(accounting['download_force_body_n']))
        st.caption(accounting['scope']+' '+accounting['transient_scope'])
        st.caption('机体系剩余力 / N：'+str(accounting['residual_force_body_n'])+
                   '；重心剩余力矩 / (N·m)：'+str(accounting['residual_moment_body_nm']))


def render(task_label, edit_design=True, hover=False, result_key=None):
    task = TASKS[task_label]
    case, batch = None, None
    input_errors = []
    if task == 'rotor':
        st.info('孤立旋翼：从当前方案中取出所选主旋翼或尾桨，给定总距、转速与来流，单独计算气动力和功率。不会自动加入另一旋翼、机身、尾翼或整机重量，也不求整机平衡。安装确定来流投影和载荷方向，重心仅用于力矩移轴。')
    else:
        st.info('整机任务：共用当前方案的主尾桨、机身、尾翼、质量与动力参数。悬停预算求功率和载荷需求；配平联立求姿态与操纵量。孤立旋翼页填写的总距和来流不会自动作为整机配平条件。')
    st.caption('本页填写本次工况；' + ('下方详细设置编辑方案参数。' if edit_design else '部件与整机参数统一在整机装配页修改。') + '各任务分别保存工况，结果对应实际提交的输入。')
    if task == 'open_loop':
        st.info(OPEN_LOOP_LABEL + '：动态入流、准定常挥舞；独立动态验证尚未完成。')
    try:
        case, batch = case_controls(task, hover=hover)
    except (ValueError, KeyError, TypeError, StopIteration, IndexError) as error:
        input_errors.append('任务输入暂不完整，请在详细设置补齐：' + str(error))
    try:
        if edit_design:
            details(task, case.get('rotor_id') if case else None)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        input_errors.append('详细设置存在结构缺项，请补齐或重新载入完整方案：' + str(error))
    errors = input_errors + designs.issues(current(), case.get('analysis') if case else None)
    if case and case.get('analysis') == 'response':
        from .perturbation import from_case
        try:
            from_case(case)
            if abs(case['duration_s'] / case['time_step_s'] - round(case['duration_s'] / case['time_step_s'])) > 1e-8:
                raise ValueError('响应时长须为时间步的整数倍。')
        except ValueError as error:
            errors.append(str(error))
    if errors:
        st.warning('暂不能运行；草稿和上次结果已保留。请修正以下参数：')
        for error in errors:
            st.error(error)
    if st.button('检查当前方案参数'):
        if not errors and case is not None:
            st.success('当前分析所需的机型和数据表检查通过；实际工况的数据域在求解时继续检查。')
    disabled = bool(errors) or case is None
    if st.button('运行分析', type='primary', disabled=disabled,
                 help='先修正上方错误，补齐当前任务所需参数。' if disabled else '使用当前草稿和工况计算。'):
        try:
            submitted = deepcopy(current())
            spec = batch() if batch else None
            with st.spinner('计算中，请等待结果…'):
                answer, files = designs.execute(submitted, case, spec)
            st.session_state['workspace-result'] = dict(
                answer=answer, files=files, design=submitted,
                fingerprint=designs.digest(submitted), input_fingerprint=input_fingerprint(submitted, case, spec),
                case=deepcopy(case), task=task)
            if result_key:
                from . import analysis_history
                record = st.session_state['workspace-result']
                record['context'] = result_key
                st.session_state.setdefault('analysis-results', {})[result_key] = record
                try:
                    record['history_id'] = analysis_history.save(record)
                except (ValueError, OSError) as error:
                    st.warning('本次结果已保留在页面，历史落盘失败，请先下载结果：' + str(error))
        except (ValueError, OSError, KeyError, TypeError) as error:
            st.error(str(error))
    if result_key:
        from . import analysis_history
        with st.expander('本任务历史结果（保留实际输入）'):
            rows = analysis_history.entries(result_key)
            names = {identifier: timestamp + ' · ' + name for identifier, timestamp, name in rows}
            selected = st.selectbox('已保存计算结果', list(names), index=0 if names else None,
                                    format_func=lambda value: names[value], key='history:'+result_key,
                                    help='只读取历史结果，不覆盖当前整机或工况。时间使用UTC，完整日期随结果保存。')
            if st.button('查看历史结果', disabled=selected is None):
                try:
                    st.session_state.setdefault('analysis-results', {})[result_key] = analysis_history.load(selected)
                except (ValueError, OSError, KeyError) as error:
                    st.error('历史结果无法读取：' + str(error))
        record = st.session_state.get('analysis-results', {}).get(result_key)
    else:
        record = st.session_state.get('workspace-result')
    if record and record['task'] == task:
        try:
            same = not disabled and record['input_fingerprint'] == input_fingerprint(current(), case, batch() if batch else None)
        except (ValueError, KeyError, TypeError):
            same = False
        show_result(record, same)
