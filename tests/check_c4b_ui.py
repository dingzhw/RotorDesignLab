"""C4-B rendered control branches, saved rig pose and old physical inputs."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from streamlit.testing.v1 import AppTest
from rotordesignlab import module_workspace as store, designs, analysis_history
from rotordesignlab.rotor_trial import basis

ROOT = Path(__file__).resolve().parents[1]


def field(items, label):
    return next(item for item in items if item.label == label)


def ok(app):
    assert not app.exception, [item.value for item in app.exception]


def main():
    with TemporaryDirectory() as folder, patch.object(store, 'LIBRARY', Path(folder)/'modules'), patch.object(designs, 'LIBRARY', Path(folder)/'aircraft'), patch.object(analysis_history, 'LIBRARY', Path(folder)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=120).run()
        ok(app)
        field(app.number_input, '向前速度 / (m/s)').set_value(10.).run()
        field(app.number_input, '向右速度 / (m/s)').set_value(3.).run()
        np.testing.assert_allclose(app.session_state['module-draft']['case']['flow_rotor_m_s'], [10., -3., 0.])
        draft = deepcopy(app.session_state['module-draft'])
        field(app.radio, '速度填写方式').set_value('空气相对桨毂速度（桨盘坐标）').run()
        assert app.session_state['module-draft'] == draft
        assert field(app.number_input, '桨盘X来流 / (m/s)').value == 10.
        assert not any(item.label in ('入流模型', '桨尖损失') for item in app.selectbox)
        assert sum(item.label == '预锥角 / °' for item in app.number_input) == 1
        field(app.selectbox, '桨叶运动方式').set_value('fixed').run()
        ok(app)
        assert '挥舞特性' not in field(app.selectbox, '旋翼参数分组').options
        assert not any(item.label.startswith('重力加速度') for item in app.number_input)
        assert '桨叶质量矩' not in field(app.selectbox, '旋翼参数分组').options
        field(app.selectbox, '桨叶运动方式').set_value('hinged').run()
        assert app.session_state['module-draft']['module']['blade_mass'] == draft['module']['blade_mass']
        field(app.number_input, '试验俯仰 / °').set_value(90.)
        field(app.button, '应用试验姿态').click().run()
        ok(app)
        saved = deepcopy(app.session_state['module-draft'])
        np.testing.assert_allclose(basis([0,90,0]) @ saved['case']['gravity_rotor_m_s2'], [0,0,9.80665], atol=1e-12)
        field(app.button, '保存').click().run()
        field(app.button, '打开所选方案').click().run()
        assert app.session_state['module-draft'] == saved
        assert store.unpack(store.pack(saved)) == saved
        # Old axial/override semantics and arbitrary local gravity survive browsing.
        old = store.template(next(iter(store.TEMPLATES)))
        old['case'].update(method='axial', flapping_model='fixed', gravity_rotor_m_s2=[1.,2.,-8.])
        old['module']['rotor']['precone_deg'] = 4.
        old['module']['flapping']['precone_deg'] = 2.
        app.session_state['module-draft'] = old
        app.session_state['module-source-snapshot'] = deepcopy(old['module'])
        app.session_state['module-epoch'] += 1
        app.run()
        ok(app)
        assert app.session_state['module-draft'] == old
        assert field(app.number_input, '预锥角 / °').value == 4.
        assert any(item.label == '入流模型' for item in app.selectbox)
        assert not any(item.label == '方位离散数' for item in app.number_input)
        assert not any(item.label.startswith('向前速度') for item in app.number_input)
        print('C4-B UI passed: velocity views, conditional fields, pose, save/reopen, old axial and precone')


if __name__ == '__main__':
    main()
