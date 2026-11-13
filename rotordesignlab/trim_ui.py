"""Local design workflow for steady helicopter trim."""
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import pandas as pd
import streamlit as st
from .cases import read_case
from .hover_ui import calculate


def render():
    base=Path(__file__).resolve().parents[1]/'examples/trim'
    preset=st.selectbox('配平模板',['200 kg 合成无人机','UH-60 公开参数与工程估计'])
    path=base/('synthetic.json' if preset.startswith('200') else 'uh60-public.json');aircraft=read_case(path)
    mode=st.radio('配平任务',['单点配平','速度曲线','速度—质量比较','速度—重心比较'],horizontal=True)
    st.caption('悬停、正爬升和无侧滑直线前飞。显示六分量残差、操纵余量和功率余量；全部结果为模型估算。')
    with st.form('trim-parameters'):
        local=st.text_input('配平机型 JSON 路径',str(path))
        a,b,c=st.columns(3)
        speed=a.number_input('水平速度 / m/s',0.,150.,0.)
        climb=b.number_input('爬升率 / m/s',0.,15.,0.)
        altitude=c.number_input('飞行高度 / m',0.,11000.,0.)
        mass=a.number_input('配平质量 / kg',.01,1e6,float(aircraft['mass_properties']['mass_kg']))
        cg=b.number_input('重心 x / m',-100.,100.,float(aircraft['mass_properties']['cg_m'][0]),format='%.3f')
        duration=c.number_input('需维持时间 / s',.001,1e9,600.)
        with st.expander('专业设置与扫描'):
            radial=st.number_input('每桨径向站数',8,2000,80)
            azimuth=st.number_input('整周方位角站数',12,720,36)
            if mode!='单点配平':
                speeds=st.text_input('速度扫描 / m/s（逗号分隔）','0,5,10,15,20')
                if mode=='速度—质量比较':groups=st.text_input('质量扫描 / kg',','.join(f'{mass*k:.6g}' for k in [.9,1,1.1]))
                if mode=='速度—重心比较':groups=st.text_input('重心 x 扫描 / m',','.join(f'{cg+k:.6g}' for k in [-.05,0,.05]))
        st.caption('推进比上限 μ=0.25；实际范围还受翼型数据域限制。UH-60 当前示例已检查至 20 m/s，30 m/s 主桨数据越界。')
        submitted=st.form_submit_button('运行整机配平',type='primary')
    if submitted:
        st.session_state.pop('trim-result',None)
        try:
            case=dict(schema_version=3,model='helicopter',analysis='trim',aircraft_json=local,
                speed_m_s=speed,climb_m_s=climb,altitude_m=altitude,mass_kg=mass,cg_x_m=cg,
                requested_duration_s=duration,radial_stations=radial,azimuth_stations=azimuth)
            batch=None
            if mode!='单点配平':
                axes={'speed_m_s':[float(v) for v in speeds.split(',')]}
                if mode in ('速度—质量比较','速度—重心比较'):
                    axes['mass_kg' if mode=='速度—质量比较' else 'cg_x_m']=[float(v) for v in groups.split(',')]
                batch=dict(schema_version=1,kind='helicopter_trim_sweep',axes=axes,continuation=True)
            with st.spinner('联立旋翼稳态与整机力、力矩平衡…'):st.session_state['trim-result']=calculate(case,batch)
        except (ValueError,OSError) as error:st.error(str(error))
    if 'trim-result' not in st.session_state:return
    answer,files=st.session_state['trim-result'];is_batch=answer.get('model')=='helicopter_trim_batch'
    with st.expander('本次实际输入与参数来源'):
        for name in ('batch.json' if is_batch else 'case.json','aircraft.json'):
            if name in files:st.json(json.loads(files[name]))
    if answer['status']!='converged':
        st.error(answer.get('error','未得到有效配平'))
        if not is_batch:st.caption(f"方程状态：{answer.get('solver_status')}；数据域：{answer.get('support_status')}；限制：{answer.get('design_limits_status')}")
    if is_batch:
        st.write(answer['summary'])
        for name in ('performance.png','controls.png'):
            if name in files:st.image(files[name])
        if 'performance.csv' in files:st.dataframe(pd.read_csv(BytesIO(files['performance.csv'])),hide_index=True)
    elif answer['status']=='converged':
        s=answer['summary'];a,b,c=st.columns(3)
        a.metric('整机需用轴功率',f"{s['required_power_w']/1000:.2f} kW")
        b.metric('对应时长的功率余量',f"{s['duration_margin_w']/1000:.2f} kW")
        c.metric('最大归一化六分量残差',f"{s['max_scaled_residual']:.2e}")
        st.write(f"求解：收敛；数据域：{answer['support_status']}；限制：{answer['design_limits_status']}；证据：模型估算。")
        if not answer['feasible']:st.warning('超过给定限制：'+', '.join(answer['violations']))
        st.dataframe(pd.read_csv(BytesIO(files['trim.csv'])),hide_index=True)
        with st.expander('操纵余量、部件载荷与内部残差'):
            st.json(answer['control_margins_deg']);st.json(answer['components']);st.json(answer['diagnostics'])
    elif 'trim-diagnostics.json' in files:st.json(json.loads(files['trim-diagnostics.json']))
    for warning in answer.get('warnings',[]):st.caption(warning)
    archive=BytesIO()
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
    st.download_button('下载配平工况、曲线与报告',archive.getvalue(),'rotordesignlab-trim.zip')
