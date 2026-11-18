"""New defaults, old draft semantics and waveform validation in the actual app."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.model_scope import OPEN_LOOP_LABEL
from check_workspace_ui import field, ok, run, replay

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix='rdl-v044-ui-') as directory, patch.object(designs, 'LIBRARY', Path(directory)):
        app = AppTest.from_file(str(ROOT / 'tests/legacy_workspace_app.py'), default_timeout=180).run()
        field(app.radio, '分析任务').set_value(OPEN_LOOP_LABEL).run()
        field(app.selectbox, '开环任务').set_value('小扰动阶跃响应').run()
        ok(app)
        assert field(app.selectbox, '扰动波形').value == 'pulse'
        assert field(app.number_input, '响应时长 / s').value == 2.
        assert field(app.number_input, '扰动开始时间 / s').value == .2
        assert field(app.number_input, '每段扰动持续时间 / s').value == .5
        assert app.session_state['design']['aircraft']['trim']['download_policy'] == 'none'
        field(app.number_input, '响应时长 / s').set_value(.1).run()
        assert field(app.button, '运行分析').disabled
        assert any('窗口' in error.value for error in app.error)
        field(app.number_input, '扰动开始时间 / s').set_value(0.).run()
        field(app.number_input, '每段扰动持续时间 / s').set_value(.05).run()
        record = run(app)
        assert record['answer']['status'] == 'converged', record['answer']
        assert record['answer']['perturbation']['type'] == 'pulse'
        assert 'input.csv' in record['files'] and 'input.png' in record['files']
        replay(record)
        # Reopening an old draft must retain its implicit step and download,
        # including a bad old duration that can be corrected on the same page.
        legacy = deepcopy(app.session_state['design'])
        legacy['settings'] = {'_workspace_revision': 3, '_active_task': OPEN_LOOP_LABEL,
                              'open_loop': {'mode': '小扰动阶跃响应', 'duration_s': .01}}
        legacy['aircraft']['trim'].pop('download_policy')
        app.session_state['design'] = legacy
        app.session_state['design_epoch'] += 1
        app.run()
        ok(app)
        assert field(app.selectbox, '扰动波形').value == 'step'
        assert field(app.number_input, '扰动开始时间 / s').value == 0.
        assert field(app.number_input, '响应时长 / s').value == .01
        assert field(app.button, '运行分析').disabled
        assert 'download_policy' not in app.session_state['design']['aircraft']['trim']
        assert any('上次运行结果' in item.value for item in app.warning)
        field(app.number_input, '响应时长 / s').set_value(.05).run()
        assert not field(app.button, '运行分析').disabled
        record = run(app)
        assert record['answer']['status'] == 'converged', record['answer']
        assert record['answer']['download_model']['strategy'] == 'legacy_fraction'
        replay(record)
        print('New pulse/default policy, invalid recovery, actual input export, old draft step/download and CLI replay passed.')


if __name__ == '__main__':
    main()
