"""M3: module calculation -> fixed installation -> aircraft tasks -> reopen."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from rotordesignlab import designs, module_workspace, analysis_history
from check_workspace_ui import field, ok, replay

ROOT = Path(__file__).resolve().parents[1]


def page(app, name):
    field(app.radio, '工作区').set_value(name).run()
    ok(app)


def run(app):
    field(app.button, '运行分析').click().run()
    ok(app)
    record = app.session_state['workspace-result']
    assert record['answer']['status'] == 'converged', record['answer']
    replay(record)
    return record


def main():
    with TemporaryDirectory() as directory, patch.object(designs, 'LIBRARY', Path(directory)/'designs'), \
            patch.object(module_workspace, 'LIBRARY', Path(directory)/'modules'), \
            patch.object(analysis_history, 'LIBRARY', Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=180).run()
        ok(app)
        field(app.number_input, '径向叶素数').set_value(24).run()
        field(app.number_input, '方位离散数').set_value(12).run()
        field(app.button, '运行旋翼计算').click().run()
        assert app.session_state['module-result']['answer']['status'] == 'converged'
        field(app.button, '保存').click().run()
        module_id = app.session_state['module-id']
        module_draft = deepcopy(app.session_state['module-draft'])
        page(app, '整机装配')
        assert app.session_state['design']['format_version'] == 2
        field(app.button, '装入所选旋翼方案').click().run()
        ok(app)
        instance = deepcopy(app.session_state['design']['assembly']['instances'][0])
        assert instance['source']['identifier'] == module_id
        assert instance['snapshot']['module'] == module_draft['module']
        assert field(app.selectbox, '旋转方向（从正推力轴端看向桨毂）').disabled
        assert '主旋翼' not in field(app.selectbox, '参数分组').options
        before = deepcopy(app.session_state['design'])
        field(app.number_input, '安装参考转速 / r/min').set_value(0.)
        field(app.button, '应用位置与传动设置').click().run()
        ok(app)
        assert any('大于零' in item.value for item in app.error)
        assert app.session_state['design'] == before
        field(app.number_input, '安装参考转速 / r/min').set_value(1700.)
        field(app.button, '应用位置与传动设置').click().run()
        ok(app)
        field(app.selectbox, '选择安装位与角色').set_value(1).run()
        field(app.number_input, '桨毂位置 x / m').set_value(-2.)
        field(app.button, '应用位置与传动设置').click().run()
        ok(app)
        assert app.session_state['design']['assembly']['instances'][0] == instance
        assert app.session_state['design']['aircraft']['rotors'][1]['position_m'][0] == -2.
        field(app.number_input, '桨毂位置 x / m').set_value(-1.7)
        field(app.selectbox, '尾桨转速定义').set_value('main_ratio').run()
        field(app.button, '应用位置与传动设置').click().run()
        ok(app)
        assert app.session_state['design']['assembly']['instances'][1]['drive']['rpm_mode'] == 'main_ratio'
        field(app.button, '检查整机装配').click().run()
        ok(app)
        assert not app.error, [e.value for e in app.error]
        field(app.button, '保存').click().run()
        ok(app)
        design_id = app.session_state['design_id']
        saved = deepcopy(app.session_state['design'])
        page(app, '悬停求解')
        assert not any(item.label == '参数分组' for item in app.selectbox)
        field(app.number_input, '每桨径向叶素数').set_value(24).run()
        budget = deepcopy(run(app))
        field(app.radio, '悬停分析方法').set_value('六分量悬停配平').run()
        field(app.number_input, '飞行高度 / m').set_value(100.).run()
        field(app.number_input, '每桨径向叶素数').set_value(24).run()
        field(app.number_input, '整周方位角站数').set_value(12).run()
        hover = deepcopy(run(app))
        assert hover['case']['speed_m_s'] == hover['case']['climb_m_s'] == 0
        assert not any(item.label == '水平速度 / (m/s)' for item in app.number_input)
        page(app, '全机配平')
        assert field(app.number_input, '飞行高度 / m').value == 0.
        field(app.number_input, '水平速度 / (m/s)').set_value(5.).run()
        field(app.number_input, '每桨径向叶素数').set_value(24).run()
        field(app.number_input, '整周方位角站数').set_value(12).run()
        trim = deepcopy(run(app))
        page(app, '开环评估')
        assert field(app.button, '运行分析').disabled
        field(app.checkbox, '仅作故障诊断，查看矩阵与响应').check().run()
        field(app.number_input, '每桨径向叶素数').set_value(24).run()
        field(app.number_input, '整周方位角站数').set_value(12).run()
        opened = run(app)
        assert opened['answer']['evaluation_restriction']['issue'] == 'R19'
        assert len(list((Path(directory)/'results').glob('*.zip'))) == 4
        page(app, '悬停求解')
        field(app.radio, '悬停分析方法').set_value('六分量悬停配平').run()
        assert field(app.number_input, '飞行高度 / m').value == 100.
        assert app.session_state['analysis-results']['hover_trim']['answer'] == hover['answer']
        field(app.radio, '悬停分析方法').set_value('功率与载荷预算').run()
        assert app.session_state['analysis-results']['hover_budget']['answer'] == budget['answer']
        # Updating a library document does not update the installed snapshot.
        new_module, revision = module_workspace.load(module_id)
        new_module['module']['rotor']['radius_m'] = 1.12
        module_workspace.save(new_module, module_id, revision)
        page(app, '整机装配')
        assert app.session_state['design']['assembly']['instances'][0]['snapshot'] == instance['snapshot']
        field(app.selectbox, '选择安装位与角色').set_value(0).run()
        field(app.button, '装入所选旋翼方案').click().run()
        assert app.session_state['design']['aircraft']['rotors'][0]['radius_m'] == 1.12
        page(app, '全机配平')
        assert any('上次运行结果' in w.value for w in app.warning)
        assert app.session_state['analysis-results']['trim']['answer'] == trim['answer']
        assert app.session_state['module-draft'] == module_draft
        # A fresh session reopens the saved assembly and immutable history.
        reopened = AppTest.from_file(str(ROOT/'app.py'), default_timeout=180).run()
        page(reopened, '全机配平')
        field(reopened.selectbox, '本机整机方案').set_value(design_id).run()
        field(reopened.button, '打开所选方案').click().run()
        field(reopened.radio, '处理未保存修改').set_value('放弃修改并继续').run()
        field(reopened.button, '确认选择').click().run()
        ok(reopened)
        assert reopened.session_state['design']['assembly'] == saved['assembly']
        field(reopened.button, '查看历史结果').click().run()
        ok(reopened)
        assert reopened.session_state['analysis-results']['trim']['answer']['summary'] == trim['answer']['summary']
        print('M3 UI passed: module to assembly, independent installations, immutable library snapshot, hover budget/trim, forward trim, R19, history and reopen.')


if __name__ == '__main__':
    main()
