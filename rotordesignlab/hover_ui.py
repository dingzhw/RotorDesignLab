"""Streamlit hover workflow, sharing CLI solvers and exported inputs."""
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import streamlit as st

from .cases import read_case, run_case, write_json
from .batch import run_batch


def calculate(case, batch=None):
    with TemporaryDirectory(prefix='rotordesignlab-hover-') as directory:
        base=Path(directory);out=base/'output'
        case=dict(case,aircraft_json=str(Path(case['aircraft_json']).resolve()))
        if batch is None:answer=run_case(case,base,out)
        else:
            write_json(base/'case.json',case)
            answer=run_batch(dict(batch,case_json='case.json'),base,out)
        return answer,{p.relative_to(out).as_posix():p.read_bytes() for p in out.rglob('*') if p.is_file()}


def render():
    base=Path(__file__).resolve().parents[1]/'examples/hover'
    preset=st.selectbox('预算模板',['200 kg 合成无人机','UH-60 公开参数（含工程估计）'])
    path=base/('synthetic.json' if preset.startswith('200') else 'uh60-public.json')
    aircraft=read_case(path)
    main,tail=aircraft['rotors']
    mode=st.radio('预算任务',['单点预算','质量—高度图','主桨尺寸—转速图','尾桨尺寸—力臂图','三方案比较'],horizontal=True)
    st.caption('功率与载荷预算：闭合垂向力和偏航力矩，显示未配平侧力。UH-60 动力曲线为工程示例。')
    with st.form('hover-parameters'):
        local=st.text_input('整机文件路径',str(path))
        left,middle,right=st.columns(3)
        mass=left.number_input('整机质量 / kg',.01,1e6,float(aircraft['mass_properties']['mass_kg']))
        altitude=middle.number_input('高度 / m',0.,11000.,0.)
        duration=right.number_input('需维持时长 / s',.001,1e9,600.)
        with st.expander('专业设置与扫描'):
            n=st.number_input('每桨径向叶素数',8,2000,240)
            if mode=='质量—高度图':
                keys=('mass_kg','altitude_m'); defaults=([mass*.8,mass,mass*1.2],[0,1500,3000])
            elif mode=='主桨尺寸—转速图':
                keys=('main_radius_m','main_rpm'); defaults=([main['radius_m']*.95,main['radius_m'],main['radius_m']*1.05],
                    [main['defaults']['rpm']*.95,main['defaults']['rpm']])
            elif mode=='尾桨尺寸—力臂图':
                keys=('tail_radius_m','tail_arm_m');arm=abs(tail['position_m'][0]-aircraft['mass_properties']['cg_m'][0])
                defaults=([tail['radius_m']*.9,tail['radius_m'],tail['radius_m']*1.1],[arm*.9,arm,arm*1.1])
            else:keys=();defaults=()
            strings=[st.text_input(f'{key}（逗号分隔；SI）',','.join(f'{v:.8g}' for v in values)) for key,values in zip(keys,defaults)]
            if mode=='三方案比较':
                variants=st.text_area('方案 JSON（半径保持实际弦长/扭转）',json.dumps([
                    dict(name='A baseline',overrides={}),
                    dict(name='B larger main',overrides=dict(main_radius_m=main['radius_m']*1.08,main_rpm=main['defaults']['rpm']/1.08)),
                    dict(name='C larger tail',overrides=dict(tail_radius_m=tail['radius_m']*1.1))],indent=2))
        submitted=st.form_submit_button('运行整机预算',type='primary')
    if submitted:
        st.session_state.pop('hover-result',None)
        try:
            case=dict(schema_version=3,model='helicopter',analysis='hover_budget',aircraft_json=local,
                      mass_kg=mass,altitude_m=altitude,requested_duration_s=duration,radial_stations=n)
            batch=None
            if keys:batch=dict(schema_version=1,kind='helicopter_sweep',axes={key:[float(v) for v in text.split(',')] for key,text in zip(keys,strings)})
            elif mode=='三方案比较':batch=dict(schema_version=1,kind='helicopter_comparison',variants=json.loads(variants))
            with st.spinner('计算主尾桨与功率收支…'):st.session_state['hover-result']=calculate(case,batch)
        except (ValueError,OSError) as error:st.error(str(error))
    if 'hover-result' not in st.session_state:return
    answer,files=st.session_state['hover-result']
    is_batch=answer.get('model')=='helicopter_batch'
    with st.expander('本次实际输入（结果对应此快照）'):
        if ('batch.json' if is_batch else 'case.json') in files:
            st.json(json.loads(files['batch.json' if is_batch else 'case.json']))
        if 'aircraft.json' in files:st.json(json.loads(files['aircraft.json']))
    if answer['status']!='converged':st.error(answer.get('error','未完成'))
    if is_batch:
        st.write(answer['summary'])
        if 'performance.png' in files:
            st.image(files['performance.png']);st.dataframe(pd.read_csv(BytesIO(files['performance.csv'])),hide_index=True)
    elif answer['status']=='converged':
        s=answer['summary'];left,middle,right=st.columns(3)
        left.metric('总需用轴功率',f"{s['required_power_w']/1000:.2f} kW")
        middle.metric('连续功率余量',f"{s['continuous_margin_w']/1000:.2f} kW")
        right.metric('尾桨推力',f"{s['tail_thrust_n']:.1f} N")
        st.write(f"求解已收敛；设计限制：{answer['design_limits_status']}；证据：模型估算。")
        if not answer['feasible']:st.warning('当前方案超过给定限制：'+', '.join(answer['violations']))
        st.dataframe(pd.read_csv(BytesIO(files['budget.csv'])),hide_index=True)
        st.caption(f"剩余力 N：{answer['residual_force_body_n']}；剩余力矩 N·m：{answer['residual_moment_body_nm']}")
    for warning in answer.get('warnings',[]):st.caption(warning)
    archive=BytesIO()
    with ZipFile(archive,'w',ZIP_DEFLATED) as bundle:
        for name,data in sorted(files.items()):bundle.writestr(name,data)
    st.download_button('下载整机工况与报告',archive.getvalue(),'rotordesignlab-hover.zip')
