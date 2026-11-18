"""M2 AppTest: independent configuration, persistence and legacy navigation."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from rotordesignlab import module_workspace as store
from rotordesignlab import designs, analysis_history
from check_workspace_ui import replay

ROOT = Path(__file__).resolve().parents[1]


def field(items, label):
    return next(item for item in items if item.label == label)


def ok(app):
    assert not app.exception, [e.value for e in app.exception]


def main():
    with TemporaryDirectory() as directory, patch.object(store, 'LIBRARY', Path(directory)/'modules'), patch.object(designs, 'LIBRARY', Path(directory)/'aircraft'), patch.object(analysis_history, 'LIBRARY', Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=120).run()
        ok(app)
        assert 'design' not in app.session_state
        initial = deepcopy(app.session_state['module-draft'])
        for group in field(app.selectbox, '旋翼参数分组').options:
            field(app.selectbox, '旋翼参数分组').select(group).run()
            ok(app)
        assert app.session_state['module-draft'] == initial, 'Browsing modified module'
        field(app.number_input, '总距 / °').set_value(12.).run()
        field(app.number_input, '径向叶素数').set_value(24).run()
        field(app.number_input, '方位离散数').set_value(12).run()
        field(app.number_input, '盘面内 x速度 / (m/s)').set_value(3.).run()
        assert app.session_state['module-draft']['case']['flow_rotor_m_s'] == [-3., 0., 0.]
        field(app.radio, '速度填写方式').set_value('空气相对桨毂速度').run()
        assert field(app.number_input, '盘面内 x速度 / (m/s)').value == -3.
        field(app.radio, '速度填写方式').set_value('旋翼相对空气运动速度').run()
        field(app.button, '运行旋翼计算').click().run()
        ok(app)
        result = deepcopy(app.session_state['module-result'])
        assert result['answer']['status'] == 'converged', result['answer']
        field(app.number_input, '总距 / °').set_value(13.).run()
        assert '当前草稿已修改' in ' '.join(e.value for e in app.subheader)
        assert app.session_state['module-result'] == result
        field(app.button, '保存').click().run()
        ok(app)
        identifier = app.session_state['module-id']
        saved = deepcopy(app.session_state['module-draft'])
        assert store.load(identifier)[0] == saved
        for page in ('整机装配', '悬停求解', '全机配平', '开环评估', '孤立旋翼'):
            field(app.radio, '工作区').set_value(page).run()
            ok(app)
        assert app.session_state['module-draft'] == saved
        assert app.session_state['module-result'] == result
        aircraft = deepcopy(app.session_state['design'])
        # New navigation still executes the shared aircraft solver and its R19 gate.
        field(app.radio, '工作区').set_value('悬停求解').run()
        field(app.button, '运行分析').click().run()
        ok(app)
        assert app.session_state['workspace-result']['answer']['status'] == 'converged'
        replay(app.session_state['workspace-result'])
        field(app.radio, '工作区').set_value('全机配平').run()
        field(app.button, '运行分析').click().run()
        ok(app)
        assert app.session_state['workspace-result']['answer']['status'] == 'converged'
        replay(app.session_state['workspace-result'])
        field(app.radio, '工作区').set_value('开环评估').run()
        assert field(app.button, '运行分析').disabled
        assert any('仅作故障诊断' in item.label for item in app.checkbox)
        field(app.radio, '工作区').set_value('孤立旋翼').run()
        aircraft = deepcopy(app.session_state['design'])
        field(app.number_input, '总距 / °').set_value(14.).run()
        assert app.session_state['design'] == aircraft
        field(app.button, '打开所选方案').click().run()
        assert app.session_state['module-draft']['case']['collective_deg'] == 14., 'Dirty draft replaced'
        field(app.radio, '处理未保存修改').set_value('放弃修改并继续').run()
        field(app.button, '确认选择').click().run()
        ok(app)
        assert app.session_state['module-draft'] == saved
        # Failed import and malformed tables must leave the draft intact.
        import streamlit as st
        from io import BytesIO
        original_upload = st.file_uploader
        def upload(title, *args, **kwargs):
            if title == '旋翼方案文件':
                bad = BytesIO(b'broken package')
                bad.name = 'broken.rdlc'
                return bad
            return original_upload(title, *args, **kwargs)
        with patch.object(st, 'file_uploader', side_effect=upload):
            app.run()
            field(app.button, '打开方案文件').click().run()
            ok(app)
            assert any('导入失败' in item.value for item in app.error)
            assert app.session_state['module-draft'] == saved
        app.run()
        field(app.selectbox, '旋翼参数分组').select('桨叶质量矩').run()
        field(app.checkbox, '填写挥舞惯量 Iβ / (kg·m²)').uncheck().run()
        field(app.button, '运行旋翼计算').click().run()
        ok(app)
        assert app.session_state['module-result']['answer']['status'] == 'failed'
        field(app.checkbox, '填写挥舞惯量 Iβ / (kg·m²)').check().run()
        field(app.number_input, '挥舞惯量 Iβ / (kg·m²)').set_value(1.2).run()
        field(app.radio, '求解任务').set_value('指定拉力反求').run()
        field(app.number_input, '目标拉力 / N').set_value(1800.).run()
        field(app.checkbox, '限定反求搜索区间').check().run()
        assert app.session_state['module-draft']['case']['target']['bounds'] == [2, 24]
        field(app.button, '运行旋翼计算').click().run()
        ok(app)
        assert app.session_state['module-result']['answer']['status'] == 'converged'
        field(app.radio, '求解任务').set_value('批量性能扫描').run()
        field(app.number_input, '点数1').set_value(2).run()
        field(app.button, '运行旋翼计算').click().run()
        ok(app)
        assert app.session_state['module-result']['answer']['status'] == 'converged'
        sweep = deepcopy(app.session_state['module-draft'])
        field(app.radio, '工作区').set_value('整机装配').run()
        field(app.radio, '工作区').set_value('孤立旋翼').run()
        ok(app)
        assert app.session_state['module-draft'] == sweep, 'Sweep changed after page switch'
        field(app.button, '保存').click().run()
        field(app.button, '打开所选方案').click().run()
        ok(app)
        assert app.session_state['module-draft'] == sweep, 'Sweep changed after reopen'
        irregular = deepcopy(sweep)
        irregular['sweep']['axes'] = {'collective_deg': [12., 12.2, 14.]}
        app.session_state['module-draft'] = irregular
        app.session_state['module-epoch'] += 1
        app.run()
        ok(app)
        assert app.session_state['module-draft']['sweep']['axes'] == {'collective_deg': [12., 12.2, 14.]}
        field(app.selectbox, '旋翼起始模板').select('UH-60 公开基准旋翼').run()
        field(app.button, '创建旋翼方案').click().run()
        if any(item.label == '处理未保存修改' for item in app.radio):
            field(app.radio, '处理未保存修改').set_value('放弃修改并继续').run()
            field(app.button, '确认选择').click().run()
        field(app.selectbox, '旋翼参数分组').select('翼型气动数据').run()
        ok(app)
        print('M2 UI passed: standalone, fields, flow, run, save/reopen, navigation, inverse, sweep, public polar')


if __name__ == '__main__':
    main()
