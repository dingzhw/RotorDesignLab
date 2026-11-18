"""Pre-M2 UI fixture for archived compatibility checks; not a product entry.

The current five-workspace app is tested by check_module_ui.py. This fixture
keeps historical model-choice/migration and form regressions executable while
the old aircraft form is still used in M3's transitional assembly pages.
"""
import streamlit as st
from rotordesignlab.design_ui import manager
from rotordesignlab.workspace_ui import TASKS, render

st.set_page_config(layout='wide')
manager()


def remember_task():
    st.session_state['design']['settings']['_active_task'] = st.session_state['analysis-task']


task = st.radio('分析任务', list(TASKS), horizontal=True, key='analysis-task', on_change=remember_task)
render(task)
