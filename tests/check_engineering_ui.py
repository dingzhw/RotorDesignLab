"""Run with Python from repository root; Streamlit needs local loopback sockets."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from streamlit.testing.v1 import AppTest

from rotordesignlab.cases import read_case, run_case


def field(elements, label):
    return next(element for element in elements if element.label == label)


app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run()
assert not app.exception, app.exception
field(app.radio, '选择算例').set_value('工程旋翼').run()
field(app.radio, '计算方式').set_value('反求总距').run()
field(app.button, '运行工况').click().run()
assert not app.exception and not app.error, (app.exception, app.error)
result, files = app.session_state['工程旋翼']
assert result['target_solution']['relative_thrust_error'] < 1e-8
assert abs(result['summary']['thrust_n'] - 2000) < 1e-6
assert len(app.get('download_button')) == 1
with TemporaryDirectory() as temporary:
    base = Path(temporary)
    for name, content in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    replay = run_case(read_case(base / 'case.json'), base, base / 'replay')
    assert replay['summary'] == result['summary']
print('UI inverse collective and exported-input replay passed', flush=True)

# Editing a form without submitting must leave the last computed result intact.
field(app.number_input, '目标拉力 / N').set_value(1e6)
assert app.session_state['工程旋翼'][0]['summary']['thrust_n'] == result['summary']['thrust_n']
assert field(app.number_input, '目标拉力 / N').value == 1e6
field(app.button, '运行工况').click().run()
assert not app.exception and len(app.error) == 1, (app.exception, app.error, app.session_state['工程旋翼'][0])
field(app.number_input, '目标拉力 / N').set_value(2000)
field(app.button, '运行工况').click().run()
assert not app.exception and not app.error
print('UI unsubmitted inputs and failed-target recovery passed', flush=True)

field(app.radio, '计算方式').set_value('反求转速').run()
field(app.button, '运行工况').click().run()
assert not app.exception and not app.error
assert app.session_state['工程旋翼'][0]['target_solution']['solve_for'] == 'rpm'
print('UI inverse RPM passed', flush=True)

for mode, counts in [('批量正算', (30, 30, 0, 7)), ('批量反求总距', (15, 11, 4, 0))]:
    field(app.radio, '计算方式').set_value(mode).run()
    field(app.button, '运行工况').click().run()
    assert not app.exception, app.exception
    result, files = app.session_state['工程旋翼']
    assert tuple(result['summary'][key] for key in ('total', 'converged', 'failed', 'limit_violations')) == counts
    assert all(name in files for name in ('batch.json', 'performance.csv', 'performance.png', 'inputs/aircraft.json'))
    assert len(app.get('download_button')) == 1
    assert bool(app.error) == bool(counts[2])
    assert json.loads(files['batch.json'])['case_json'] == 'inputs/case.json'
    print(f'UI {mode}: {counts} passed', flush=True)

print('All engineering UI checks passed', flush=True)
