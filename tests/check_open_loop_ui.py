"""Open-loop form submission, portable exports and failure recovery."""
from pathlib import Path
from tempfile import TemporaryDirectory
from streamlit.testing.v1 import AppTest
from rotordesignlab.cases import read_case,run_case

ROOT=Path(__file__).resolve().parents[1]
def field(items,label):return next(i for i in items if i.label==label)

print('Opening application',flush=True)
app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
print('Selecting open-loop form',flush=True)
field(app.radio,'选择算例').set_value('通用开环操稳').run()
print('Running linearization',flush=True)
field(app.button,'运行开环分析').click().run()
assert not app.exception,app.exception
r,files=app.session_state['open-loop-result'];assert r['status']=='converged',r
assert all(k in files for k in ('A.csv','B.csv','E.csv','linearization.json','modes.png','frequency.svg','case.json','trim/aircraft.json'))
print('Replaying exported input',flush=True)
with TemporaryDirectory() as temp:
    base=Path(temp)
    for name,data in files.items():
        p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    replay=run_case(read_case(base/'case.json'),base,base/'replay');assert replay['linearization']==r['linearization']
field(app.number_input,'开环基点速度 / m/s').set_value(50.)
assert app.session_state['open-loop-result'][0]['trim']['summary']['speed_m_s']==20
print('Checking failure state',flush=True)
field(app.button,'运行开环分析').click().run()
assert app.session_state['open-loop-result'][0]['status']=='failed'
field(app.number_input,'开环基点速度 / m/s').set_value(0.)
print('Checking recovery',flush=True)
field(app.button,'运行开环分析').click().run()
assert app.session_state['open-loop-result'][0]['status']=='converged'
print('Checking response form and plot',flush=True)
field(app.selectbox,'开环模板').set_value('UH-60 公开部件模型').run()
field(app.radio,'开环任务').set_value('小扰动阶跃响应').run()
field(app.number_input,'响应时长 / s').set_value(.05)
field(app.button,'运行开环分析').click().run()
r,files=app.session_state['open-loop-result']
assert r['status']=='converged',r
assert r['analysis']=='response' and 'response.png' in files and 'response.csv' in files
assert 'response_error_state_scales' in r
assert len(app.get('download_button'))==1 and not app.exception,app.exception
print('Open-loop UI: submitted input, CLI replay, failure recovery, matrix/figure export passed.')
