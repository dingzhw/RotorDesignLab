"""Exercise form submission, error recovery and exported cases via Streamlit AppTest."""
from pathlib import Path
from tempfile import TemporaryDirectory

from streamlit.testing.v1 import AppTest
from rotordesignlab.cases import read_case,run_case

ROOT=Path(__file__).resolve().parents[1]


def widget(collection,label):return next(item for item in collection if item.label==label)


app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
widget(app.radio,'选择算例').set_value('整机悬停预算').run()
widget(app.button,'运行整机预算').click().run()
assert not app.exception,app.exception
result,files=app.session_state['hover-result'];assert result['status']=='converged',result
with TemporaryDirectory() as directory:
    root=Path(directory)
    for name,data in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    replay=run_case(read_case(root/'case.json'),root,root/'replay')
    assert replay['summary']==result['summary']
widget(app.number_input,'整机质量 / kg').set_value(900.)
widget(app.button,'运行整机预算').click().run()
assert app.session_state['hover-result'][0]['status']=='failed'
widget(app.number_input,'整机质量 / kg').set_value(200.)
widget(app.button,'运行整机预算').click().run()
assert app.session_state['hover-result'][0]['status']=='converged'
widget(app.radio,'预算任务').set_value('三方案比较').run()
widget(app.button,'运行整机预算').click().run()
assert not app.exception,app.exception
result,files=app.session_state['hover-result'];assert result['summary']['converged']==3,result
widget(app.radio,'预算任务').set_value('质量—高度图').run()
widget(app.text_input,'mass_kg（逗号分隔；SI）').set_value('bad')
widget(app.button,'运行整机预算').click().run()
assert 'hover-result' not in app.session_state,'Stale result survived invalid new submission'
widget(app.text_input,'mass_kg（逗号分隔；SI）').set_value('180,200')
widget(app.button,'运行整机预算').click().run()
assert app.session_state['hover-result'][0]['summary']['total']==6
assert not app.exception,app.exception
print('Hover UI: point, replay, failure/recovery, comparison, invalid-input/stale-result checks passed.')
