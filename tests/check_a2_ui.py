"""Real Streamlit script check for explicit model/ownership, missing data and replay."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs, module_workspace, analysis_history, assembly
from check_workspace_ui import field, ok, replay


with TemporaryDirectory() as temporary, patch.object(designs,'LIBRARY',Path(temporary)/'designs'), \
        patch.object(module_workspace,'LIBRARY',Path(temporary)/'modules'), \
        patch.object(analysis_history,'LIBRARY',Path(temporary)/'history'):
    app=AppTest.from_file(str(designs.ROOT/'app.py'),default_timeout=180).run()
    field(app.radio,'工作区').set_value('整机装配').run()
    ok(app)
    field(app.selectbox,'整机载荷与动力学模型').set_value('harmonic_hub_v1')
    field(app.button,'应用动力学模型与质量归属').click().run()
    ok(app)
    assert any('填写来源' in item.value for item in app.error)
    assert 'dynamics' not in app.session_state['design']['aircraft']
    # Template supplies explicit synthetic mass distribution, not inferred data.
    selectors=[item for item in app.selectbox if item.label == '整机起始模板']
    assert len(selectors)==1
    selectors[0].set_value('千机-200轻型无人直升机（A2质量分账，试验性）')
    field(app.button,'创建整机方案').click().run()
    field(app.radio,'处理未保存修改').set_value('放弃修改并继续')
    field(app.button,'确认选择').click().run()
    ok(app)
    assert not app.error,[item.value for item in app.error]
    good=deepcopy(app.session_state['design'])
    field(app.button,'保存').click().run()
    ok(app)
    identifier=app.session_state['design_id']
    restored,_=designs.load_design(identifier)
    assert restored['aircraft']['dynamics']==good['aircraft']['dynamics']
    field(app.radio,'工作区').set_value('开环评估').run()
    assert field(app.button,'运行分析').disabled
    field(app.checkbox,'仅作故障诊断，查看矩阵与响应').check().run()
    field(app.number_input,'每桨径向叶素数').set_value(24).run()
    field(app.number_input,'整周方位角站数').set_value(24).run()
    field(app.button,'运行分析').click().run()
    ok(app)
    record=app.session_state['workspace-result']
    assert record['answer']['status']=='converged',record['answer']
    assert record['answer']['summary']['states']==21
    assert record['answer']['evaluation_restriction']['issue']=='R19'
    replay(record)
    field(app.radio,'工作区').set_value('整机装配').run()
    field(app.selectbox,'整机载荷与动力学模型').set_value('legacy_aero_v1')
    field(app.button,'应用动力学模型与质量归属').click().run()
    ok(app)
    assert 'dynamics' not in app.session_state['design']['aircraft']
    assert app.session_state['design']['assembly']['instances'][0]['snapshot']==good['assembly']['instances'][0]['snapshot']
    assert app.session_state['analysis-results']['open_loop']['answer']['summary']['states']==21
    print('A2 UI passed: explicit ownership, synthetic example, save/reopen, 21-state computation/replay, legacy switch, preserved snapshot and R19.')
