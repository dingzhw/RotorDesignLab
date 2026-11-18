"""RotorDesignLab: independent component and aircraft workspaces."""
import streamlit as st
from rotordesignlab import __version__
from rotordesignlab.design_ui import manager, details
from rotordesignlab.workspace_ui import TASKS,render

st.set_page_config(page_title='RotorDesignLab｜旋翼设计台',layout='wide')
st.title('RotorDesignLab｜旋翼设计台')
st.caption(f'{__version__} · 旋翼模块 → 整机装配 → 工况分析 → 保存与复算')
page = st.sidebar.radio('工作区', ['孤立旋翼', '整机装配', '悬停求解', '全机配平', '开环评估'],
                        key='workspace-page', help='旋翼模块与整机方案分别保存草稿，切换工作区不会互相覆盖。')
with st.sidebar.expander('基准验证（高级）'):
    reference=st.checkbox('打开原 Julia UH-60 80 kt 基准',value=False)
    st.caption('保留原模型的历史复算入口；日常设计分析使用右侧统一方案。')
if reference:
    from rotordesignlab.reference_ui import render as render_reference
    render_reference()
elif page == '孤立旋翼':
    from rotordesignlab.module_ui import render as render_module
    render_module()
elif page == '整机装配':
    st.info('当前保留已有整机方案编辑；加载独立模块、绑定安装实例与快照的装配流程将在M3接通。')
    manager()
    details()
else:
    manager()
    if page == '悬停求解':
        st.caption('本页当前提供功率与载荷预算；悬停六分量平衡可在全机配平中设前飞速度和爬升率为0。M3接通装配后的独立分析流程。')
        task = '整机悬停预算'
    elif page == '全机配平':
        task = '整机配平'
    else:
        task = next(k for k, v in TASKS.items() if v == 'open_loop')
    render(task)
