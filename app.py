"""RotorDesignLab: independent component and aircraft workspaces."""
import streamlit as st
from rotordesignlab import __version__
from rotordesignlab.workspace_ui import TASKS,render

st.set_page_config(page_title='RotorDesignLab｜旋翼设计台',layout='wide')
st.title('RotorDesignLab｜旋翼设计台')
st.caption(f'{__version__} · 旋翼模块 → 整机装配 → 工况分析 → 保存与复算')
from rotordesignlab.template_audit import panel
panel()
if 'pending-workspace' in st.session_state:
    st.session_state['workspace-page'] = st.session_state.pop('pending-workspace')
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
    from rotordesignlab.assembly_ui import render as render_assembly
    render_assembly()
else:
    from rotordesignlab.assembly_ui import analysis_header
    if not analysis_header():
        st.stop()
    hover = False
    if page == '悬停求解':
        kind = st.radio('悬停分析方法', ['功率与载荷预算', '六分量悬停配平'], horizontal=True,
                        help='预算闭合垂向与反扭矩收支；六分量配平同时求姿态和操纵，两个方法分别保存工况与结果。')
        hover = kind == '六分量悬停配平'
        task = '整机配平' if hover else '整机悬停预算'
        context = 'hover_trim' if hover else 'hover_budget'
    elif page == '全机配平':
        task = '整机配平'
        context = 'trim'
    else:
        task = next(k for k, v in TASKS.items() if v == 'open_loop')
        context = 'open_loop'
    render(task, edit_design=False, hover=hover, result_key=context)
