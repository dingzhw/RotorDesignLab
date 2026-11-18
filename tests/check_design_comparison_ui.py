"""Same-task comparison through the modern page, history and portable export."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs, module_workspace, analysis_history
from rotordesignlab.comparison_ui import LABEL
from check_workspace_ui import field, ok, replay

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory() as directory, \
            patch.object(designs, 'LIBRARY', Path(directory)/'designs'), \
            patch.object(module_workspace, 'LIBRARY', Path(directory)/'modules'), \
            patch.object(analysis_history, 'LIBRARY', Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=120).run()
        field(app.radio, '工作区').set_value('全机配平').run()
        field(app.selectbox, '配平任务').set_value(LABEL).run()
        ok(app)
        field(app.number_input, '每桨径向叶素数').set_value(24).run()
        field(app.number_input, '整周方位角站数').set_value(12).run()
        field(app.number_input, '水平速度 / (m/s)').set_value(15.).run()
        field(app.text_input, '候选2 来源与估算说明').set_value('网页保存检查：尺寸敏感性估算，结构质量未更新。').run()
        field(app.button, '运行分析').click().run()
        ok(app)
        record = deepcopy(app.session_state['workspace-result'])
        assert record['answer']['status'] == 'converged', record['answer']
        assert len(record['answer']['candidates']) == 3
        assert {'design-comparison.csv', 'performance.png', 'controls.png', 'report.md'} <= record['files'].keys()
        replay(record)
        restored = analysis_history.load(record['history_id'])
        assert restored['answer']['candidates'] == record['answer']['candidates']
        restored_design = designs.unpack(record['files']['design.rdl'])
        assert restored_design['settings']['design-comparison'] == record['design']['settings']['design-comparison']
        field(app.number_input, '候选2 主桨半径 / m').set_value(.03).run()
        assert app.session_state['workspace-result']['answer'] == record['answer']
        assert any('上次运行结果' in item.value for item in app.warning)
        field(app.button, '运行分析').click().run()
        ok(app)
        assert app.session_state['workspace-result']['answer']['status'] == 'partial'
        field(app.number_input, '候选2 主桨半径 / m').set_value(1.155).run()
        field(app.button, '运行分析').click().run()
        ok(app)
        assert app.session_state['workspace-result']['answer']['status'] == 'converged'
        # The same configured candidates are available for a separate hover task.
        field(app.radio, '工作区').set_value('悬停求解').run()
        field(app.selectbox, '预算任务').set_value(LABEL).run()
        field(app.button, '运行分析').click().run()
        ok(app)
        latest = app.session_state['workspace-result']['answer']
        assert latest['common_task']['speed_m_s'] == 0.
        assert latest['status'] == 'converged'
        print('同任务三方案：网页、历史重开、导出复算、草稿隔离、失败修正和悬停入口通过')


if __name__ == '__main__':
    main()
