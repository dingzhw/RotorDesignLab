"""CSV upload boundary: Chinese headers, application and failure preservation."""
from io import BytesIO,StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.parameter_fields import label
from check_workspace_ui import field,ok,ROOT

with TemporaryDirectory() as tmp,patch.object(designs,'LIBRARY',Path(tmp)):
    original=st.file_uploader;payload=None
    def upload(title,*args,**kwargs):
        if title=='载入桨叶几何 CSV':return BytesIO(payload) if payload else None
        return original(title,*args,**kwargs)
    with patch.object(st,'file_uploader',side_effect=upload):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
        field(app.selectbox,'参数分组').set_value('主旋翼').run()
        field(app.radio,'旋翼设置内容').set_value('桨叶几何表').run();ok(app)
        name=app.session_state['design']['aircraft']['rotors'][0]['geometry_csv']
        frame=pd.read_csv(StringIO(app.session_state['design']['assets'][name]));frame.loc[0,'chord_m']=.114
        payload=frame.rename(columns={k:label(k) for k in frame.columns}).to_csv(index=False).encode('utf-8-sig')
        app.run();field(app.button,'应用桨叶几何 CSV').click().run();ok(app)
        good=app.session_state['design']['assets'][name]
        assert '0.114' in good
        payload=b'wrong,header\n1,2\n'
        app.run();field(app.button,'应用桨叶几何 CSV').click().run();ok(app)
        assert any('列名' in e.value for e in app.error)
        assert app.session_state['design']['assets'][name]==good
print('Chinese CSV header mapping and invalid-file preservation passed.')
