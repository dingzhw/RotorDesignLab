"""C4-A: actual UI branching, lossless schemes and independent assembly input."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from rotordesignlab import module_workspace as store, designs, analysis_history, assembly
from rotordesignlab.module_manager_ui import new_scheme

ROOT = Path(__file__).resolve().parents[1]


def field(items, label):
    return next(item for item in items if item.label == label)


def check(app):
    assert not app.exception, [item.value for item in app.exception]


def main():
    with TemporaryDirectory() as folder, \
            patch.object(store, 'LIBRARY', Path(folder)/'rotors'), \
            patch.object(designs, 'LIBRARY', Path(folder)/'aircraft'), \
            patch.object(analysis_history, 'LIBRARY', Path(folder)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=120).run()
        check(app)
        assert not any('允许替换' in item.label for item in app.checkbox)
        assert not any('本机旋翼方案' == item.label for item in app.selectbox)
        original = deepcopy(app.session_state['module-draft'])
        assert all(k not in original['module']['rotor']['limits'] for k in ('power_w', 'torque_nm'))
        assert original == new_scheme(next(iter(store.TEMPLATES)))
        field(app.number_input, '径向叶素数').set_value(24).run()
        field(app.number_input, '方位离散数').set_value(12).run()
        assert any('系数 θc' in item.label for item in app.number_input)
        field(app.radio, '求解任务').set_value('指定拉力反求').run()
        assert not any(item.label == '总距 / °' for item in app.number_input)
        assert any(item.label == '转速 / (r/min)' for item in app.number_input)
        field(app.checkbox, '限定反求搜索区间').check().run()
        field(app.selectbox, '反求变量').set_value('rpm').run()
        check(app)
        assert not any(item.label == '转速 / (r/min)' for item in app.number_input)
        assert any(item.label == '总距 / °' for item in app.number_input)
        assert app.session_state['module-draft']['case']['target']['bounds'] == original['module']['rotor']['limits']['rpm']
        field(app.number_input, '目标拉力 / N').set_value(1800.).run()
        field(app.button, '运行旋翼计算').click().run()
        check(app)
        answer = app.session_state['module-result']['answer']
        assert answer['status'] == 'converged', answer
        assert answer['design_limits_status'] == 'not_evaluated'
        assert answer['feasible'] is None
        target = deepcopy(app.session_state['module-draft']['case']['target'])
        field(app.radio, '求解任务').set_value('给定操纵正算').run()
        field(app.radio, '求解任务').set_value('指定拉力反求').run()
        assert app.session_state['module-draft']['case']['target'] == target
        field(app.radio, '求解任务').set_value('批量性能扫描').run()
        assert not any(item.label == '总距 / °' for item in app.number_input)
        field(app.selectbox, '扫描参数1').set_value('flow_x').run()
        assert not any(item.label == '桨盘X来流 / (m/s)' for item in app.number_input)
        field(app.button, '保存').click().run()
        check(app)
        saved = deepcopy(app.session_state['module-draft'])
        first_id = app.session_state['module-id']
        field(app.button, '复制方案').click().run()
        assert app.session_state['module-id'] != first_id
        assert store.load(first_id)[0] == saved
        field(app.number_input, '总距 / °').set_value(saved['case']['collective_deg']+1.).run()
        changed = deepcopy(app.session_state['module-draft'])
        field(app.button, '打开所选方案').click().run()
        assert app.session_state['module-draft'] == changed
        field(app.button, '确认选择').click().run()  # cancel
        assert app.session_state['module-draft'] == changed
        field(app.button, '打开所选方案').click().run()
        field(app.radio, '处理未保存修改').set_value('放弃修改并继续').run()
        field(app.button, '确认选择').click().run()
        assert app.session_state['module-draft'] == saved
        package = store.pack(saved)
        assert store.unpack(package) == saved
        # The actual assembly file-upload callback must extract only the component.
        field(app.radio, '工作区').set_value('整机装配').run()
        before = deepcopy(app.session_state['design'])
        def upload(title, *args, **kwargs):
            if title == '旋翼方案文件':
                stream = BytesIO(package)
                stream.name = 'rotor-scheme.rdlc'
                return stream
            return None
        with patch('streamlit.file_uploader', side_effect=upload):
            app.run()
            field(app.button, '装入所选旋翼文件').click().run()
            check(app)
        after = app.session_state['design']
        module, assets = assembly.module_data(after['assembly']['instances'][0])
        assert module == saved['module'] and assets == saved['assets']
        assert before['settings'] == after['settings'], 'isolated conditions leaked into aircraft'
        # Opening a historical scheme must retain its limits.
        field(app.radio, '工作区').set_value('孤立旋翼').run()
        legacy = store.template(next(iter(store.TEMPLATES)))
        def legacy_upload(title, *args, **kwargs):
            if title == '旋翼方案文件':
                stream = BytesIO(store.pack(legacy))
                stream.name = 'legacy.rdlc'
                return stream
            return None
        with patch('streamlit.file_uploader', side_effect=legacy_upload):
            app.run()
            field(app.button, '打开方案文件').click().run()
            check(app)
        assert app.session_state['module-draft'] == legacy
        field(app.button, '保存').click().run()
        legacy_id = app.session_state['module-id']
        field(app.number_input, '总距 / °').set_value(legacy['case']['collective_deg']+1.).run()
        edited = deepcopy(app.session_state['module-draft'])
        field(app.button, '创建旋翼方案').click().run()
        field(app.radio, '处理未保存修改').set_value('保存后继续').run()
        field(app.button, '确认选择').click().run()
        check(app)
        assert store.load(legacy_id)[0] == edited
        assert app.session_state['module-draft'] == new_scheme(next(iter(store.TEMPLATES)))
        print('C4-A passed: task inputs, optional limits, bounds, drafts, copy/open, same-file assembly, old limits')


if __name__ == '__main__':
    main()
