"""Same-assembly comparison, stored history and portable replay via the page."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs, module_workspace, analysis_history
from check_workspace_ui import field, ok, replay

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory() as directory, \
            patch.object(designs, 'LIBRARY', Path(directory)/'designs'), \
            patch.object(module_workspace, 'LIBRARY', Path(directory)/'modules'), \
            patch.object(analysis_history, 'LIBRARY', Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=120).run()
        field(app.radio, '工作区').set_value('悬停求解').run()
        field(app.selectbox, '预算任务').set_value('预算—配平功率对照').run()
        field(app.number_input, '每桨径向叶素数').set_value(24).run()
        field(app.number_input, '整周方位角站数').set_value(12).run()
        field(app.button, '运行分析').click().run()
        ok(app)
        record = deepcopy(app.session_state['workspace-result'])
        assert record['answer']['status'] == 'converged', record['answer']
        assert record['answer']['analysis'] == 'hover_comparison'
        assert 'power-comparison.csv' in record['files']
        assert len(record['answer']['assumptions']) == 4
        replay(record)
        restored = analysis_history.load(record['history_id'])
        assert restored['answer']['methods'] == record['answer']['methods']
        field(app.number_input, '需维持时间 / s').set_value(60.).run()
        assert app.session_state['workspace-result']['answer'] == record['answer']
        assert any('上次运行结果' in item.value for item in app.warning)
        field(app.button, '运行分析').click().run()
        ok(app)
        latest = app.session_state['workspace-result']['answer']
        assert all(v['power_accounting']['rating'] == 'short_time' for v in latest['methods'].values())
        print('功率对照网页、历史重开、导出复算及未提交输入隔离通过')


if __name__ == '__main__':
    main()
