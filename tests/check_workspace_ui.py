"""Unified design workflow integration checks (requires local loopback)."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs
from rotordesignlab.cases import run_case,read_case

ROOT=Path(__file__).resolve().parents[1]

def field(items,label):return next(i for i in items if i.label==label)
def ok(app):assert not app.exception,[e.value for e in app.exception]
def choose(app,group):field(app.selectbox,'参数分组').set_value(group).run();ok(app)
def run(app):field(app.button,'运行分析').click().run();ok(app);return app.session_state['workspace-result']


def editor_checks(app):
    initial=deepcopy(app.session_state['design'])
    for group in field(app.selectbox,'参数分组').options:
        choose(app,group)
        if group in ('主旋翼','尾桨'):
            for page in ('桨叶几何表','翼型气动表','参数与操纵'):
                field(app.radio,'旋翼设置内容').set_value(page).run();ok(app)
        if group=='平尾与垂尾':field(app.selectbox,'选择尾翼').set_value(1).run();ok(app)
    assert app.session_state['design']==initial,'Merely visiting fields modified input data'
    choose(app,'质量、重心与惯量')
    matrix=deepcopy(app.session_state['design']['aircraft']['mass_properties']['inertia_cg_kg_m2'])
    field(app.checkbox,'填写重心惯量张量 / (kg·m²)').uncheck().run()
    assert 'inertia_cg_kg_m2' not in app.session_state['design']['aircraft']['mass_properties']
    field(app.checkbox,'填写重心惯量张量 / (kg·m²)').check().run();ok(app)
    assert app.session_state['design']['aircraft']['mass_properties']['inertia_cg_kg_m2']==matrix
    field(app.number_input,'整机质量 / kg').set_value(205.).run();ok(app)
    choose(app,'主旋翼')
    field(app.number_input,'旋翼半径 R / m').set_value(1.12).run();ok(app)
    field(app.radio,'旋翼设置内容').set_value('桨叶几何表').run()
    epoch=app.session_state['design_epoch'];name=app.session_state['design']['aircraft']['rotors'][0]['geometry_csv']
    key=f'd:{epoch}:assets/{name}'
    app.session_state[key]={'edited_rows':{0:{'chord_m':.106}},'added_rows':[],'deleted_rows':[]}
    app.run();ok(app)
    assert '0.106' in app.session_state['design']['assets'][name]
    asset=app.session_state['design']['assets'][name];app.run()
    assert asset==app.session_state['design']['assets'][name]
    choose(app,'质量、重心与惯量')
    assert field(app.number_input,'整机质量 / kg').value==205.
    field(app.number_input,'整机质量 / kg').set_value(-1.).run();ok(app)
    assert any('整机质量' in e.value for e in app.error)
    assert field(app.button,'运行分析').disabled
    assert field(app.number_input,'本次总距 θ₀ / °')
    field(app.number_input,'整机质量 / kg').set_value(200.).run();ok(app)
    # Inject a data-editor delta; the resulting widget table is read back into the draft.
    epoch=app.session_state['design_epoch'];key=f'd:{epoch}:aircraft/mass_properties/cg_m'
    app.session_state[key]={'edited_rows':{0:{'x':.01}},'added_rows':[],'deleted_rows':[]}
    app.run();ok(app)
    assert app.session_state['design']['aircraft']['mass_properties']['cg_m'][0]==.01
    app.run();assert app.session_state['design']['aircraft']['mass_properties']['cg_m'][0]==.01
    choose(app,'动力与传动')
    key=f'd:{epoch}:aircraft/powerplant/_table'
    app.session_state[key]={'edited_rows':{0:{'continuous_power_w':46000}},'added_rows':[],'deleted_rows':[]}
    app.run();ok(app)
    assert app.session_state['design']['aircraft']['powerplant']['continuous_power_w'][0]==46000
    choose(app,'基本信息')
    field(app.text_input,'方案名称').set_value('界面保存重开检查').run()
    field(app.button,'保存方案').click().run();ok(app)
    identifier=app.session_state['design_id'];saved=deepcopy(app.session_state['design'])
    choose(app,'质量、重心与惯量')
    field(app.number_input,'整机质量 / kg').set_value(220.).run()
    field(app.button,'重新打开').click().run();ok(app)
    assert app.session_state['design']['aircraft']['mass_properties']['mass_kg']==220.,'Unsaved work discarded'
    field(app.checkbox,'确认替换当前草稿（新建、重开、导入或恢复模板时使用）').check().run()
    field(app.button,'重新打开').click().run();ok(app)
    assert app.session_state['design']==saved
    # All four tasks use the same current design.
    for task in ('整机悬停预算','整机配平','开环初评（低频模型·试验性）','孤立旋翼'):
        field(app.radio,'分析任务').set_value(task).run();ok(app)
        assert app.session_state['design_id']==identifier
        assert app.session_state['design']['aircraft']==saved['aircraft']
    print('Editor groups, neutral viewing, invalid input, table edits, save/reopen and task switching passed.',flush=True)


def replay(record):
    with TemporaryDirectory() as temporary:
        root=Path(temporary)
        for name,data in record['files'].items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        if 'batch.json' in record['files']:
            from rotordesignlab.batch import run_batch
            result=run_batch(read_case(root/'batch.json'),root,root/'replay')
        else:result=run_case(read_case(root/'case.json'),root,root/'replay')
        assert result['status']==record['answer']['status'],result
        assert result.get('summary')==record['answer'].get('summary')
        if 'linearization' in result:assert result['linearization']==record['answer']['linearization']
        assert designs.unpack((root/'design.rdl').read_bytes())==record['design']


def analysis_checks(app,tasks=None):
    tasks=tasks or ['孤立旋翼','整机悬停预算','整机配平','开环初评（低频模型·试验性）']
    for task in tasks:
        field(app.radio,'分析任务').set_value(task).run();ok(app)
        record=run(app);assert record['answer']['status']=='converged',record['answer']
        replay(record)
        print(task+': submitted input and CLI replay passed.',flush=True)
    if '孤立旋翼' in tasks:
        field(app.radio,'分析任务').set_value('孤立旋翼').run()
        previous = run(app)
        choose(app,'质量、重心与惯量')
        old_mass = app.session_state['design']['aircraft']['mass_properties']['mass_kg']
        field(app.number_input,'整机质量 / kg').set_value(-1.).run()
        ok(app)
        assert field(app.button,'运行分析').disabled
        assert app.session_state['workspace-result']['input_fingerprint'] == previous['input_fingerprint']
        assert any('上次运行结果' in w.value for w in app.warning)
        assert field(app.number_input,'本次总距 θ₀ / °')
        field(app.number_input,'整机质量 / kg').set_value(old_mass).run()
        ok(app)
        assert not field(app.button,'运行分析').disabled
        assert run(app)['answer']['summary'] == previous['answer']['summary']
        field(app.selectbox,'旋翼计算方式').set_value('指定拉力反求总距').run()
        record=run(app);assert record['answer']['status']=='converged',record['answer']
        assert abs(record['answer']['summary']['thrust_n']-2000)<1e-5
        field(app.number_input,'目标拉力 / N').set_value(1e6).run()
        assert any('上次运行结果' in w.value for w in app.warning)
        record=run(app);assert record['answer']['status']=='failed'
        field(app.number_input,'目标拉力 / N').set_value(2000).run()
        assert run(app)['answer']['status']=='converged'
        field(app.selectbox,'旋翼计算方式').set_value('批量正算').run()
        field(app.text_input,'总距扫描 / °').set_value('12,16').run()
        field(app.text_input,'转速扫描 / rpm').set_value('1700').run()
        record=run(app);assert record['answer']['summary']['total']==2;replay(record)
    if '整机悬停预算' in tasks:
        field(app.radio,'分析任务').set_value('整机悬停预算').run()
        field(app.selectbox,'预算任务').set_value('三方案比较').run()
        record=run(app);assert record['answer']['summary']['total']==3,record['answer'];replay(record)
    if '整机配平' in tasks:
        field(app.radio,'分析任务').set_value('整机配平').run()
        field(app.selectbox,'配平任务').set_value('速度曲线').run()
        field(app.text_input,'速度扫描 / (m/s)').set_value('0,5').run()
        record=run(app);assert record['answer']['summary']['total']==2,record['answer'];replay(record)
    if '开环初评（低频模型·试验性）' in tasks:
        field(app.radio,'分析任务').set_value('开环初评（低频模型·试验性）').run()
        field(app.selectbox,'开环任务').set_value('小扰动阶跃响应').run()
        field(app.selectbox, '扰动波形').set_value('step').run()
        field(app.number_input, '扰动开始时间 / s').set_value(0.).run()
        field(app.number_input,'响应时长 / s').set_value(.05).run()
        record=run(app);assert record['answer']['status']=='converged',record['answer']
        assert 'response.png' in record['files'];replay(record)
    print('Inverse thrust, failure recovery, stale-result notice and table-driven comparisons passed.',flush=True)


def main(tasks=None):
    with TemporaryDirectory(prefix='rdl-ui-library-') as library,patch.object(designs,'LIBRARY',Path(library)):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run();ok(app)
        assert field(app.radio,'分析任务').options==['孤立旋翼','整机悬停预算','整机配平','开环初评（低频模型·试验性）']
        assert not any('JSON' in w.label for w in app.text_input)
        editor_checks(app)
        analysis_checks(app,tasks)
        field(app.radio,'分析任务').set_value('整机配平').run()
        field(app.selectbox,'配平任务').set_value('单点配平').run()
        field(app.number_input,'水平速度 / (m/s)').set_value(5.).run()
        field(app.number_input,'每桨径向叶素数').set_value(24).run()
        field(app.button,'保存方案').click().run();ok(app)
        saved_id=app.session_state['design_id'];expected=deepcopy(app.session_state['design'])
        # A fresh browser session loads both the model and its last task/case.
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        field(app.selectbox,'已保存方案').set_value(saved_id).run()
        field(app.checkbox,'确认替换当前草稿（新建、重开、导入或恢复模板时使用）').check().run()
        field(app.button,'重新打开').click().run();ok(app)
        assert app.session_state['design']==expected
        assert field(app.radio,'分析任务').value=='整机配平'
        assert field(app.number_input,'水平速度 / (m/s)').value==5.
        assert field(app.number_input,'每桨径向叶素数').value==24
        replay(run(app))
        print('Fresh-session reopen restored model, last analysis, case settings and numerical replay.',flush=True)
        # UH-60 field groups preserve the full-angle/Re grids without silently changing inputs.
        field(app.selectbox,'新建所用模板').set_value(list(designs.TEMPLATES)[1]).run()
        field(app.checkbox,'确认替换当前草稿（新建、重开、导入或恢复模板时使用）').check().run()
        field(app.button,'从模板新建').click().run();ok(app)
        original=deepcopy(app.session_state['design'])
        for group in field(app.selectbox,'参数分组').options:
            choose(app,group)
            if group in ('主旋翼','尾桨'):
                field(app.radio,'旋翼设置内容').set_value('翼型气动表').run();ok(app)
                field(app.selectbox,'气动系数').set_value('cd').run();ok(app)
        assert app.session_state['design']==original,'Public tables changed on view'
        field(app.radio,'分析任务').set_value('整机配平').run()
        record=run(app);assert record['answer']['status']=='converged',record['answer'];replay(record)
        field(app.checkbox,'打开原 Julia UH-60 80 kt 基准').check().run();ok(app)
        assert any(b.label=='运行 Julia 基准' for b in app.button)
        assert app.session_state['design']['aircraft']==original['aircraft']
        assert app.session_state['design']['assets']==original['assets']
        print('Public UH-60 field preservation, trim replay and isolated Julia reference entry passed.',flush=True)
        field(app.checkbox,'打开原 Julia UH-60 80 kt 基准').uncheck().run()
        field(app.selectbox,'新建所用模板').set_value(list(designs.TEMPLATES)[2]).run()
        field(app.checkbox,'确认替换当前草稿（新建、重开、导入或恢复模板时使用）').check().run()
        field(app.button,'从模板新建').click().run();ok(app)
        for group in field(app.selectbox,'参数分组').options:choose(app,group)
        field(app.selectbox,'来流与旋翼模型').set_value('轴流性能（原均匀/环带模型）').run()
        record=run(app);assert record['answer']['status']=='converged',record['answer']
        with TemporaryDirectory() as temp:
            source=ROOT/'examples/engineering-rotor.json'
            old=run_case(read_case(source),source.parent,Path(temp)/'old')
            assert old['summary']==record['answer']['summary']
        print('Merged three-blade/engineering entry matches original engineering case.',flush=True)


if __name__=='__main__':main()
