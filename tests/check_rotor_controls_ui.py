"""Daily rotor inputs remain visible without opening detailed settings."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from check_workspace_ui import field,ok,run,replay,ROOT

with TemporaryDirectory() as tmp,patch.object(designs,'LIBRARY',Path(tmp)):
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run();ok(app)
    # Inspect the ordinary page, without opening or selecting any parameter group.
    pitch=field(app.number_input,'本次总距 θ₀ / °')
    rpm=field(app.number_input,'本次旋翼转速 / rpm')
    assert pitch.value==13 and rpm.value==1700
    assert pitch.proto.help and rpm.proto.help
    pitch.set_value(14.).run();rpm=field(app.number_input,'本次旋翼转速 / rpm')
    rpm.set_value(1750.).run();ok(app)
    record=run(app);assert record['answer']['status']=='converged',record['answer']
    assert record['case']['collective_deg']==14 and record['case']['rpm']==1750
    replay(record)
    field(app.selectbox,'选择分析旋翼').set_value('tail').run();ok(app)
    assert field(app.number_input,'本次总距 θ₀ / °').value==12
    field(app.selectbox,'选择分析旋翼').set_value('main').run();ok(app)
    assert field(app.number_input,'本次总距 θ₀ / °').value==14
    for widget in list(app.number_input)+list(app.selectbox):
        assert widget.proto.help,widget.label+' missing help'
print('Visible pitch/RPM, operating overrides, rotor switching, help and CLI replay passed.')
