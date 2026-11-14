"""RotorDesignLab: one design and four analysis tasks."""
import streamlit as st
from rotordesignlab import __version__
from rotordesignlab.design_ui import manager
from rotordesignlab.workspace_ui import TASKS,render

st.set_page_config(page_title='RotorDesignLab｜旋翼设计台',layout='wide')
st.title('RotorDesignLab｜旋翼设计台')
st.caption(f'{__version__} · 选择方案 → 详细设置 → 选择分析任务 → 运行与导出')
with st.sidebar.expander('基准验证（高级）'):
    reference=st.checkbox('打开原 Julia UH-60 80 kt 基准',value=False)
    st.caption('保留原模型的历史复算入口；日常设计分析使用右侧统一方案。')
if reference:
    from rotordesignlab.reference_ui import render as render_reference
    render_reference()
else:
    manager()
    def remember_task():
        st.session_state['design']['settings']['_active_task']=st.session_state['analysis-task']
    task=st.radio('分析任务',list(TASKS),horizontal=True,key='analysis-task',on_change=remember_task,
                  help='孤立旋翼：给定操纵求载荷；悬停预算：估算功率收支；整机配平：求平衡操纵；开环操稳：在配平点分析小扰动。')
    render(task)
