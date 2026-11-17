"""Actual Streamlit execution: ambiguous migration, explicit choice and guard."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.design_models import AXIAL, SPATIAL
from rotordesignlab.model_scope import OPEN_LOOP_LABEL
from check_workspace_ui import field, ok, ROOT

with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)):
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
    ok(app)
    old = deepcopy(app.session_state['design'])
    old['settings'] = {'_workspace_revision': 3}
    app.session_state['design'] = old
    app.session_state['design_epoch'] += 1
    app.run()
    ok(app)
    assert field(app.button, '运行分析').disabled
    field(app.selectbox, '来流与旋翼模型').set_value(AXIAL).run()
    assert not field(app.button, '运行分析').disabled
    field(app.button, '运行分析').click().run()
    ok(app)
    assert app.session_state['workspace-result']['case']['model'] == 'aircraft_rotor'
    saved = designs.unpack(designs.pack(app.session_state['design']))
    assert saved['settings']['rotor']['flow_model'] == AXIAL
    app.session_state['design'] = saved
    app.session_state['design_epoch'] += 1
    app.run()
    assert field(app.selectbox, '来流与旋翼模型').value == AXIAL
    # The task selector is identified by available options, not its label.
    task = next(item for item in app.radio if OPEN_LOOP_LABEL in item.options)
    task.set_value(OPEN_LOOP_LABEL).run()
    ok(app)
    assert field(app.button, '运行分析').disabled
    field(app.checkbox, '仅作故障诊断，查看矩阵与响应').check().run()
    field(app.button, '运行分析').click().run()
    ok(app)
    result = app.session_state['workspace-result']
    assert result['case']['diagnostic_only'] is True
    assert result['answer']['evaluation_restriction']['issue'] == 'R19'
    assert not any(item.label == '不稳定特征根数' for item in app.metric)
    assert any('交叉耦合待修复' in item.value for item in app.warning)
    print('Ambiguous model blocked; explicit axial choice survives reopen; diagnostic opt-in and result restriction passed.')
