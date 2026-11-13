"""Form/CLI parity, unsubmitted-input behavior, failure recovery and scan export."""
from pathlib import Path
from tempfile import TemporaryDirectory
from streamlit.testing.v1 import AppTest
from rotordesignlab.cases import read_case,run_case

ROOT=Path(__file__).resolve().parents[1]
def field(items,label):return next(i for i in items if i.label==label)

app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
field(app.radio,'选择算例').set_value('整机配平').run()
field(app.button,'运行整机配平').click().run()
assert not app.exception,app.exception
r,files=app.session_state['trim-result'];assert r['status']=='converged',r
with TemporaryDirectory() as temp:
    base=Path(temp)
    for name,data in files.items():
        p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    replay=run_case(read_case(base/'case.json'),base,base/'replay');assert replay['summary']==r['summary']
field(app.number_input,'水平速度 / m/s').set_value(50.)
assert app.session_state['trim-result'][0]['summary']['speed_m_s']==0
field(app.button,'运行整机配平').click().run()
assert app.session_state['trim-result'][0]['status']=='failed'
field(app.number_input,'水平速度 / m/s').set_value(10.)
field(app.button,'运行整机配平').click().run()
assert app.session_state['trim-result'][0]['status']=='converged'
field(app.radio,'配平任务').set_value('速度—重心比较').run()
field(app.text_input,'速度扫描 / m/s（逗号分隔）').set_value('bad')
field(app.button,'运行整机配平').click().run()
assert 'trim-result' not in app.session_state
field(app.text_input,'速度扫描 / m/s（逗号分隔）').set_value('0,10')
field(app.button,'运行整机配平').click().run()
r,files=app.session_state['trim-result']
assert r['summary']['converged']==6,r
assert all(k in files for k in ('batch.json','performance.csv','performance.png','controls.svg','report.md'))
assert len(app.get('download_button'))==1 and not app.exception,app.exception
print('Trim UI: form, snapshot, CLI replay, failure recovery, stale result, CG scan and export checks passed.')
