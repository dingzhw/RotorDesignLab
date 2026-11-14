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
    assert record['case']['model']=='spatial_rotor'
    for axis,value in zip('XYZ',[-15.,-4.,3.]):
        field(app.number_input,'来流 '+axis+' 分量 / (m/s)').set_value(value).run();ok(app)
    record=run(app);assert record['answer']['status']=='converged',record['answer']
    assert record['case']['flow_body_m_s']==[-15.,-4.,3.]
    assert abs(record['answer']['installation']['force_body_n'][1])>.1
    assert 'azimuth.png' in record['files'];replay(record)
    field(app.selectbox,'选择分析旋翼').set_value('tail').run();ok(app)
    assert field(app.number_input,'本次总距 θ₀ / °').value==12
    field(app.selectbox,'选择分析旋翼').set_value('main').run();ok(app)
    assert field(app.number_input,'本次总距 θ₀ / °').value==14
    for widget in list(app.number_input)+list(app.selectbox):
        assert widget.proto.help,widget.label+' missing help'
    field(app.selectbox,'旋翼计算方式').set_value('批量正算').run()
    field(app.selectbox,'扫描变量').set_value('flow_x_m_s').run()
    field(app.text_input,'X方向来流 / (m/s)（扫描值）').set_value('0,-15').run()
    field(app.text_input,'转速扫描 / rpm').set_value('1750').run()
    record=run(app);assert record['answer']['summary']['total']==2;replay(record)
print('Visible pitch/RPM, XYZ flow and loads, rotor switching, help, flow scan and CLI replay passed.')
