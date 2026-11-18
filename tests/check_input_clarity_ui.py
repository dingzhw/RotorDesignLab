"""One atmospheric editor, task scope, legacy preservation and replay."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.environment import standard, AIR_FIELDS
from check_workspace_ui import field, ok, run, replay, ROOT


with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)):
    app = AppTest.from_file(str(ROOT / 'tests/legacy_workspace_app.py'), default_timeout=180).run()
    ok(app)
    assert field(app.selectbox, '参数分组').options == ['主旋翼', '基本信息']
    assert not any('填写当地声速' in c.label for c in app.checkbox)
    assert not any(c.label == '当地声速 / (m/s)' for c in app.number_input)
    before = deepcopy(app.session_state['design']['aircraft'])
    field(app.number_input, '飞行高度 / m').set_value(3000.).run()
    field(app.number_input, '相对ISA温差 / °C').set_value(15.).run()
    answer = run(app)
    for key in AIR_FIELDS:
        assert answer['answer']['atmosphere'][key] == standard(3000, 15)[key]
    assert app.session_state['design']['aircraft'] == before
    replay(answer)
    field(app.selectbox, '选择分析旋翼').set_value('tail').run()
    ok(app)
    assert field(app.selectbox, '参数分组').options == ['尾桨', '基本信息']
    field(app.selectbox, '环境输入方式').set_value('custom').run()
    assert len([c for c in app.number_input if c.label == '声速 / (m/s)']) == 1
    field(app.number_input, '声速 / (m/s)').set_value(350.).run()
    field(app.button, '保存方案').click().run()
    saved = deepcopy(app.session_state['design'])
    field(app.button, '重新打开').click().run()
    assert app.session_state['design'] == saved
    assert field(app.number_input, '声速 / (m/s)').value == 350.
    field(app.checkbox, '查看整机及其他旋翼参数').check().run()
    field(app.selectbox, '参数分组').set_value('质量、重心与惯量').run()
    ok(app)
    assert app.session_state['design']['aircraft'] == before
    # An old package's nonstandard atmosphere remains the actual custom default.
    legacy = deepcopy(saved)
    legacy['settings'] = {'_workspace_revision': 4, 'rotor': {'density_kg_m3': 1.05}}
    legacy['aircraft']['rotors'][0]['speed_of_sound_m_s'] = 333.
    app.session_state['design'] = designs.unpack(designs.pack(legacy))
    app.session_state['design_epoch'] += 1
    app.run()
    assert field(app.selectbox, '环境输入方式').value == 'custom'
    assert field(app.number_input, '声速 / (m/s)').value == 333.
    assert app.session_state['design']['aircraft'] == legacy['aircraft']
    replay(run(app))
    print('Task scope, single atmosphere editor, ISA, save/reopen, legacy custom values and CLI replay passed.')
