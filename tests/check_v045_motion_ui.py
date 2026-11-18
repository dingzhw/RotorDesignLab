"""Actual Streamlit view switching, save/reopen, old drafts and CLI replay."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.coordinates import motion_to_flow
from check_workspace_ui import field, ok, run, replay, ROOT


with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)):
    app = AppTest.from_file(str(ROOT / 'tests/legacy_workspace_app.py'), default_timeout=120).run()
    ok(app)
    assert field(app.selectbox, '速度输入视角').value == 'motion'
    for title, value in [('水平前向速度 / (m/s)', 12.), ('水平右向速度 / (m/s)', 1.), ('上升速度 / (m/s)', 3.),
                         ('机体滚转角 / °', 6.), ('机体俯仰角 / °', -4.)]:
        field(app.number_input, title).set_value(value).run()
        ok(app)
    record = run(app)
    assert record['answer']['status'] == 'converged', record['answer']
    replay(record)
    expected = motion_to_flow([12., 1., 3.], [6., -4.])
    for _ in range(2):
        field(app.selectbox, '速度输入视角').set_value('flow').run()
        ok(app)
        actual = [field(app.number_input, '来流 ' + axis + ' 分量 / (m/s)').value for axis in 'XYZ']
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        assert not any('上次运行结果' in warning.value for warning in app.warning)
        field(app.selectbox, '速度输入视角').set_value('motion').run()
        ok(app)
        assert not any('上次运行结果' in warning.value for warning in app.warning)
        np.testing.assert_allclose([field(app.number_input, name).value for name in
                                   ('水平前向速度 / (m/s)', '水平右向速度 / (m/s)', '上升速度 / (m/s)')], [12, 1, 3])
    field(app.button, '保存方案').click().run()
    saved = deepcopy(app.session_state['design'])
    field(app.number_input, '水平前向速度 / (m/s)').set_value(15.).run()
    field(app.checkbox, '确认替换当前草稿（新建、重开、导入或恢复模板时使用）').check().run()
    field(app.button, '重新打开').click().run()
    ok(app)
    assert app.session_state['design'] == saved
    assert field(app.selectbox, '速度输入视角').value == 'motion'
    replay(run(app))
    legacy = deepcopy(saved)
    legacy['settings'] = {'_workspace_revision': 4, 'rotor': {'flow_x_m_s': -12., 'flow_y_m_s': -1., 'flow_z_m_s': 3.}}
    app.session_state['design'] = legacy
    app.session_state['design_epoch'] += 1
    app.run()
    ok(app)
    assert field(app.selectbox, '速度输入视角').value == 'flow'
    assert field(app.number_input, '来流 X 分量 / (m/s)').value == -12.
    assert field(app.number_input, '机体俯仰角 / °').value == 0.
    replay(run(app))
    print('Motion/XYZ view conversions, unchanged result fingerprint, attitude, save/reopen, legacy view and replay passed.')
