"""Local open-loop analysis workflow using the same portable case API."""
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import pandas as pd
import streamlit as st
from .cases import read_case
from .dynamics import CONTROLS
from .hover_ui import calculate


def render():
    base=Path(__file__).resolve().parents[1]/'examples/public-helicopter'
    preset=st.selectbox('开环模板',['200 kg 合成无人机','UH-60 公开部件模型'])
    name='synthetic' if preset.startswith('200') else 'uh60-public';path=base/f'{name}.json'
    aircraft=read_case(path)
    mode=st.radio('开环任务',['线化、模态与频响','小扰动阶跃响应'],horizontal=True)
    st.caption('低频模型估算：六自由度机体、动态入流、准定常挥舞。输入为叶片变距角；完整动态挥舞和惯性耦合仍待补充。')
    with st.form('open-loop-parameters'):
        local=st.text_input('开环机型 JSON 路径',str(path))
        a,b,c=st.columns(3)
        speed=a.number_input('开环基点速度 / m/s',0.,150.,20.)
        altitude=b.number_input('开环高度 / m',0.,11000.,0.)
        mass=c.number_input('开环质量 / kg',.01,1e6,float(aircraft['mass_properties']['mass_kg']))
        cg=a.number_input('开环重心 x / m',-100.,100.,float(aircraft['mass_properties']['cg_m'][0]),format='%.3f')
        climb=b.number_input('开环爬升率 / m/s',0.,15.,0.)
        with st.expander('网格与扰动设置'):
            radial=st.number_input('开环径向站数',8,2000,80)
            azimuth=st.number_input('开环方位角站数',12,720,36)
            if mode=='小扰动阶跃响应':
                control=st.selectbox('阶跃操纵',CONTROLS,format_func=lambda x:dict(zip(CONTROLS,['主桨总距','主桨 cos 周期变距','主桨 sin 周期变距','尾桨总距']))[x])
                amplitude=st.number_input('阶跃幅值 / deg',-2.,2.,.05,format='%.3f')
                duration=st.number_input('响应时长 / s',.05,10.,.5)
                step=st.selectbox('响应时间步 / s',[.01,.005,.002,.001,.0005],index=3 if name=='synthetic' else 0)
        submitted=st.form_submit_button('运行开环分析',type='primary')
    if submitted:
        st.session_state.pop('open-loop-result',None)
        try:
            case=dict(schema_version=3,model='helicopter',analysis='linearize' if mode.startswith('线化') else 'response',
                aircraft_json=local,speed_m_s=speed,climb_m_s=climb,altitude_m=altitude,mass_kg=mass,cg_x_m=cg,
                requested_duration_s=600,radial_stations=radial,azimuth_stations=azimuth)
            if case['analysis']=='response':case.update(control=control,amplitude_deg=amplitude,duration_s=duration,time_step_s=step)
            with st.spinner('求解配平、计算导数与开环响应…'):st.session_state['open-loop-result']=calculate(case)
        except (ValueError,OSError) as error:st.error(str(error))
    if 'open-loop-result' not in st.session_state:return
    answer,files=st.session_state['open-loop-result']
    with st.expander('本次实际输入与参数来源'):
        for filename in ('case.json','trim/aircraft.json'):
            if filename in files:st.json(json.loads(files[filename]))
    if answer['status']!='converged':st.error(answer.get('error','开环分析未通过检查'))
    else:
        s=answer['summary'];a,b,c=st.columns(3)
        a.metric('模型状态数',s['states']);b.metric('不稳定特征根数',s['unstable_modes']);c.metric('运动学中性根数',s['neutral_modes'])
        actual=answer['trim']['summary'];st.caption(f"实际基点：{actual['speed_m_s']:g} m/s，{actual['mass_kg']:g} kg；数据域：{answer['support_status']}；限制：{answer['design_limits_status']}。")
        if not answer['feasible']:st.warning('基点超过给定设计限制：'+', '.join(answer['violations']))
        if 'modes.png' in files:st.image(files['modes.png'])
        st.dataframe(pd.read_csv(BytesIO(files['modes.csv'])),hide_index=True)
        st.caption('图中仅显示低频根；表中保留快速入流模态。共轭根分别计数，稳定性结论仍需完整动态模型和公开数据进一步核查。')
        for name in ('frequency.png','response.png'):
            if name in files:st.image(files[name])
        with st.expander('操纵余量、差分检查与状态定义'):
            st.json(answer['trim']['control_margins_deg']);st.json(answer['linearization'])
    archive=BytesIO()
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
    st.download_button('下载开环矩阵、曲线与工况',archive.getvalue(),'rotordesignlab-open-loop.zip')
