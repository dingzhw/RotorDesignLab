"""Retained Julia benchmark, separated from the unified Python design workflow."""
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import altair as alt
import pandas as pd
import streamlit as st
from .cases import UH60,read_case,run_case


def render():
    st.subheader('原 Julia UH-60 80 kt 基准验证')
    st.caption('原37状态模型用于论文和历史结果复算；固定公开UH-60输入，独立于当前方案。通用Python整机模型具有不同状态和适用范围，不将两者视为等价。')
    with st.form('legacy-reference'):
        duration=st.number_input('基准仿真时长 / s',.1,3.,1.,.1)
        step=st.selectbox('基准积分步长 / s',[.02,.01,.005,.0025],index=1)
        run=st.form_submit_button('运行 Julia 基准')
    if run:
        st.session_state.pop('legacy-result',None)
        case=dict(read_case(UH60),duration_s=duration,time_step_s=step)
        with st.spinner('等待 Julia 基准计算…'),TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'output';answer=run_case(case,root,out)
            st.session_state['legacy-result']=(answer,{p.name:p.read_bytes() for p in out.iterdir() if p.is_file()})
    if 'legacy-result' not in st.session_state:return
    answer,files=st.session_state['legacy-result']
    if answer['status']=='converged':
        st.metric('配平加权残差',f"{answer['summary']['weighted_trim_residual']:.3e}")
        if 'trim_controls.csv' in files:
            controls=pd.read_csv(BytesIO(files['trim_controls.csv']))
            controls['control']=['横向杆','纵向杆','总距杆','脚蹬']
            st.dataframe(controls.rename(columns={'control':'操纵','value_pct':'操纵量 / %'}),hide_index=True)
        method=st.radio('线化口径',['固定方位','方位平均'],horizontal=True)
        method='fixed_azimuth' if method=='固定方位' else 'azimuth_average'
        channels={'横向杆 → p':'p_lateral','纵向杆 → q':'q_longitudinal','脚蹬 → r':'r_pedal'}
        channel=channels[st.selectbox('基准通道',list(channels))]
        data=pd.read_csv(BytesIO(files[method+'_frequency.csv']))
        for suffix,title in [('_db','幅值 / dB'),('_phase_deg','相位 / °')]:
            st.altair_chart(alt.Chart(data).mark_line().encode(x=alt.X('frequency_rad_s',title='角频率 / (rad/s)',scale=alt.Scale(type='log')),y=alt.Y(channel+suffix,title=title)),width='stretch')
        response=pd.read_csv(BytesIO(files['open_loop.csv']))
        st.altair_chart(alt.Chart(response).mark_line().encode(x=alt.X('time_s',title='时间 / s'),y=alt.Y('p_rad_s',title='滚转角速度 p / (rad/s)')),width='stretch')
        st.caption('幅值按角速度rad/s对操纵百分比计；以上曲线对应下载包中的实际工况。')
    else:st.error(answer.get('error','基准运行失败'))
    stream=BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    st.download_button('下载基准结果与工况',stream.getvalue(),'uh60-reference.zip')
