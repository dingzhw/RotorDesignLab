"""Environmental controls and displayed kW survive save/reopen and CLI replay."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.environment import standard, AIR_FIELDS
from check_workspace_ui import field, ok, run, replay, ROOT


with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)):
    app = AppTest.from_file(str(ROOT / 'tests/legacy_workspace_app.py'), default_timeout=180).run()
    ok(app)
    assert field(app.selectbox, '环境输入方式').value == 'isa'
    field(app.number_input, '飞行高度 / m').set_value(3000.).run()
    field(app.number_input, '相对ISA温差 / °C').set_value(15.).run()
    record = run(app)
    answer = record['answer']
    assert answer['status'] == 'converged', answer
    expected = standard(3000., 15.)
    for key in AIR_FIELDS:
        assert answer['atmosphere'][key] == expected[key]
    replay(record)
    # Simulate widgets left by the old W UI during a source hot reload.
    epoch = app.session_state['design_epoch']
    app.session_state[f'd:{epoch}:aircraft/powerplant/accessory_power_w'] = 999000.
    app.session_state[f'd:{epoch}:aircraft/powerplant/_table'] = {'edited_rows': {0: {'continuous_power_w': 999000}}, 'added_rows': [], 'deleted_rows': []}
    field(app.checkbox, '查看整机及其他旋翼参数').check().run()
    field(app.selectbox, '参数分组').set_value('动力与传动').run()
    original = app.session_state['design']['aircraft']['powerplant']['accessory_power_w']
    assert field(app.number_input, '附件耗功 / kW').value == original / 1000
    field(app.number_input, '附件耗功 / kW').set_value(1.25).run()
    assert app.session_state['design']['aircraft']['powerplant']['accessory_power_w'] == 1250
    field(app.button, '保存方案').click().run()
    saved = deepcopy(app.session_state['design'])
    field(app.button, '重新打开').click().run()
    ok(app)
    assert app.session_state['design'] == saved
    assert field(app.number_input, '相对ISA温差 / °C').value == 15.
    field(app.selectbox, '环境输入方式').set_value('custom').run()
    for title, key in [('空气密度 / (kg/m³)', 'density_kg_m3'), ('声速 / (m/s)', 'speed_of_sound_m_s'), ('动力黏度 / (Pa·s)', 'dynamic_viscosity_pa_s')]:
        field(app.number_input, title).set_value(expected[key]).run()
    custom = run(app)
    assert custom['answer']['summary'] == answer['summary']
    replay(custom)
    legacy = deepcopy(saved)
    legacy['settings'] = {'_workspace_revision': 4, 'rotor': {'density_kg_m3': 1.05}}
    app.session_state['design'] = legacy
    app.session_state['design_epoch'] += 1
    app.run()
    ok(app)
    assert field(app.selectbox, '环境输入方式').value == 'custom'
    assert field(app.number_input, '空气密度 / (kg/m³)').value == 1.05
    assert field(app.number_input, '声速 / (m/s)').value == 340.3
    assert field(app.number_input, '动力黏度 / (Pa·s)').value == 1.7894e-5
    replay(run(app))
    print('ISA+temperature and custom environment, exact CLI replay, displayed kW/SI save, reopen and old atmosphere defaults passed.')
