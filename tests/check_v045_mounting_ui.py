"""Actual parameter editing, persistence and legacy no-mutation in Streamlit."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.mounting import tilt_basis
from rotordesignlab.coordinates import selected_basis
from check_workspace_ui import field, ok, run, replay, ROOT


with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)):
    app = AppTest.from_file(str(ROOT / 'tests/legacy_workspace_app.py'), default_timeout=150).run()
    ok(app)
    for template in list(designs.TEMPLATES)[:2]:
        app.session_state['design'] = designs.from_template(template)
        app.session_state['design_epoch'] += 1
        app.run()
        field(app.checkbox, '查看整机及其他旋翼参数').check().run()
        field(app.selectbox, '参数分组').set_value('主旋翼').run()
        ok(app)
        assert field(app.number_input, '零方位绕轴偏置 / °').value == 0.
        field(app.number_input, '主轴前倾角 / °').set_value(5.)
        field(app.number_input, '主轴右倾角 / °').set_value(-4.)
        field(app.number_input, '零方位绕轴偏置 / °').set_value(12.)
        field(app.selectbox, '旋转方向（从正推力轴端看向桨毂）').set_value(-1)
        field(app.button, '应用安装角').click().run()
        ok(app)
        np.testing.assert_allclose(selected_basis(app.session_state['design']['aircraft']['rotors'][0]), tilt_basis('main', 5, -4, 12), atol=1e-14)
        assert app.session_state['design']['aircraft']['rotors'][0]['rotation_sign'] == -1
        field(app.selectbox, '参数分组').set_value('尾桨').run()
        field(app.number_input, '尾桨轴向前偏角 / °').set_value(2.)
        field(app.number_input, '尾桨轴向上偏角 / °').set_value(3.)
        field(app.button, '应用安装角').click().run()
        ok(app)
        np.testing.assert_allclose(selected_basis(app.session_state['design']['aircraft']['rotors'][1]), tilt_basis('tail', 2, 3, 0), atol=1e-14)
        field(app.button, '保存方案').click().run()
        saved = deepcopy(app.session_state['design'])
        field(app.button, '重新打开').click().run()
        ok(app)
        assert app.session_state['design'] == saved
        replay(run(app))
    # An old, forward-zero model remains byte-for-byte equivalent in its data.
    template = next(iter(designs.TEMPLATES))
    with patch.dict(designs.TEMPLATES, {template: ROOT / 'examples/templates/v044/synthetic.json'}):
        legacy = designs.from_template(template)
    app.session_state['design'] = legacy
    app.session_state['design_epoch'] += 1
    app.run()
    before = deepcopy(app.session_state['design']['aircraft'])
    field(app.selectbox, '参数分组').set_value('主旋翼').run()
    ok(app)
    assert abs(field(app.number_input, '零方位绕轴偏置 / °').value) == 180.
    assert app.session_state['design']['aircraft'] == before
    replay(run(app))
    print('Two-template main/tail installation angles, rotation, save/reopen/replay and old forward-zero preservation passed.')
