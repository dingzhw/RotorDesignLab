from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=60).run()
before = deepcopy(app.session_state['module-draft'])
selector = next(item for item in app.selectbox if item.label=='查看起始模板依据')
for name in selector.options:
    selector.set_value(name).run()
    assert not app.exception
    assert app.session_state['module-draft']==before
print('All six source notes shown without modifying the rotor draft')
