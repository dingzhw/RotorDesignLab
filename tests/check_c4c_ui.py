"""Shared aircraft scheme identity and conditional inputs across five entries."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs, module_workspace, analysis_history
from rotordesignlab import aircraft_library

ROOT = Path(__file__).resolve().parents[1]


def field(items, label):
    return next(item for item in items if item.label == label)


def ok(app):
    assert not app.exception, [item.value for item in app.exception]


def main():
    with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)/'designs'), patch.object(module_workspace, 'LIBRARY', Path(directory)/'rotors'), patch.object(analysis_history, 'LIBRARY', Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=180).run()
        rotor = deepcopy(app.session_state['module-draft'])
        field(app.radio, '工作区').set_value('整机装配').run()
        field(app.button, '保存').click().run()
        original_id = app.session_state['design_id']
        saved = deepcopy(app.session_state['design'])
        for page in ('悬停求解', '全机配平', '开环评估', '整机装配'):
            field(app.radio, '工作区').set_value(page).run()
            ok(app)
            assert app.session_state['design_id'] == original_id
            assert app.session_state['design']['assembly'] == saved['assembly']
            assert any(item.label == '整机方案名称' for item in app.text_input)
            for action in ('保存', '复制方案', '打开所选方案'):
                field(app.button, action)
            assert not any('允许替换' in item.label for item in app.checkbox)
            if page == '开环评估':
                assert field(app.button, '运行分析').disabled
        field(app.selectbox, '选择安装位与角色').set_value(1).run()
        field(app.selectbox, '尾桨转速定义').set_value('main_ratio').run()
        assert not any(item.label == '安装参考转速 / r/min' for item in app.number_input)
        field(app.number_input, '尾桨/主桨转速比').set_value(3.)
        field(app.button, '应用位置与传动设置').click().run()
        ok(app)
        aircraft = app.session_state['design']['aircraft']
        assert aircraft['rotors'][1]['defaults']['rpm'] == 3*aircraft['rotors'][0]['defaults']['rpm']
        field(app.selectbox, '尾桨转速定义').set_value('given').run()
        assert not any(item.label == '尾桨/主桨转速比' for item in app.number_input)
        before = deepcopy(app.session_state['design'])
        field(app.button, '打开所选方案').click().run()
        field(app.button, '确认选择').click().run()  # cancel
        assert app.session_state['design'] == before
        field(app.button, '复制方案').click().run()
        assert app.session_state['design_id'] != original_id
        assert designs.load_design(original_id)[0] == saved
        def bad_upload(title, *args, **kwargs):
            if title == '整机方案文件':
                return BytesIO(b'invalid')
            return None
        with patch('streamlit.file_uploader', side_effect=bad_upload):
            app.run()
            field(app.button, '打开方案文件').click().run()
            ok(app)
            assert any('导入失败' in item.value for item in app.error)
            assert app.session_state['design'] == before
        app.run()
        identifier = app.session_state['design_id']
        stale = app.session_state['design_version']
        field(app.text_input, '整机方案名称').set_value('同任务装配副本').run()
        field(app.button, '保存').click().run()
        field(app.selectbox, '本机整机方案').set_value(identifier).run()
        field(app.text_input, '整机方案名称').set_value('保存后重开自身').run()
        field(app.button, '打开所选方案').click().run()
        field(app.radio, '处理未保存修改').set_value('保存后继续')
        field(app.button, '确认选择').click().run()
        assert app.session_state['design']['aircraft']['name'] == '保存后重开自身'
        assert app.session_state['saved_fingerprint'] == designs.digest(app.session_state['design'])
        # Restore the original copy snapshot explicitly, not the latest history item.
        history_path = Path(designs.LIBRARY)/'history'/(identifier+'-'+stale+'.rdl')
        assert history_path.is_file()
        field(app.selectbox, '历史版本').set_value(history_path).run()
        field(app.button, '恢复历史到草稿').click().run()
        assert app.session_state['design'] == before
        assert app.session_state['saved_fingerprint'] != designs.digest(before)
        field(app.button, '打开所选方案').click().run()
        field(app.radio, '处理未保存修改').set_value('取消')
        field(app.button, '确认选择').click().run()
        try:
            aircraft_library.trash(identifier, stale)
        except ValueError:
            pass
        else:
            raise AssertionError('stale delete accepted')
        field(app.button, '将已保存版本移入回收区').click().run()
        assert identifier in dict(aircraft_library.deleted())
        field(app.button, '恢复为副本').click().run()
        assert len(designs.saved_designs()) == 2
        field(app.radio, '工作区').set_value('全机配平').run()
        field(app.selectbox, '配平任务').set_value('速度曲线').run()
        assert not any(item.label == '水平速度 / (m/s)' for item in app.number_input)
        field(app.radio, '工作区').set_value('悬停求解').run()
        field(app.selectbox, '预算任务').set_value('质量—高度图').run()
        assert not any(item.label == '飞行高度 / m' for item in app.number_input)
        field(app.radio, '工作区').set_value('孤立旋翼').run()
        assert app.session_state['module-draft'] == rotor
        field(app.button, '保存').click().run()
        field(app.text_input, '旋翼方案名称').set_value('旋翼保存后重开').run()
        field(app.button, '打开所选方案').click().run()
        field(app.radio, '处理未保存修改').set_value('保存后继续')
        field(app.button, '确认选择').click().run()
        assert app.session_state['module-draft']['module']['name'] == '旋翼保存后重开'
        assert app.session_state['module-saved-digest'] == module_workspace.digest(app.session_state['module-draft'])
        # A legacy aircraft file is read as-is, without converting its model or layout.
        legacy = designs.from_template(next(iter(designs.TEMPLATES)))
        archive = designs.pack(legacy)
        field(app.radio, '工作区').set_value('整机装配').run()
        with patch('streamlit.file_uploader', side_effect=lambda title, *a, **k: BytesIO(archive) if title == '整机方案文件' else None):
            app.run()
            field(app.button, '打开方案文件').click().run()
            if 'aircraft-pending' in app.session_state:
                field(app.radio, '处理未保存修改').set_value('放弃修改并继续')
                field(app.button, '确认选择').click().run()
            ok(app)
            assert app.session_state['design'] == legacy
            field(app.button, '保存').click().run()
            assert designs.load_design(app.session_state['design_id'])[0] == legacy
        print('C4-C UI passed: shared actions/identity, independent drafts, recovery, drive/scan fields, R19')


if __name__ == '__main__':
    main()
