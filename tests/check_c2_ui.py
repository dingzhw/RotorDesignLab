"""C2 geometry/import/range interaction; no live user library is touched."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pandas as pd
import json
from streamlit.testing.v1 import AppTest
from rotordesignlab import designs, module_workspace, analysis_history
from rotordesignlab.engineering_inputs import export_table
from check_workspace_ui import field, ok, replay

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory() as directory, \
            patch.object(designs,'LIBRARY',Path(directory)/'designs'), \
            patch.object(module_workspace,'LIBRARY',Path(directory)/'modules'), \
            patch.object(analysis_history,'LIBRARY',Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        initial = deepcopy(app.session_state['module-draft'])
        field(app.selectbox,'旋翼参数分组').set_value('几何与翼型数据表').run()
        ok(app)
        assert app.session_state['module-draft'] == initial
        field(app.number_input,'有效桨根扭转 / °').set_value(10.).run()
        field(app.number_input,'桨尖扭转 / °').set_value(-4.).run()
        field(app.button,'应用生成几何').click().run()
        ok(app)
        changed = deepcopy(app.session_state['module-draft'])
        assert changed['assets']['geometry.csv'] != initial['assets']['geometry.csv']
        assert changed['module']['blade_mass'] == initial['module']['blade_mass']
        content = export_table(pd.read_csv(BytesIO(changed['assets']['geometry.csv'])),'中文导入验证')
        def upload(title, *args, **kwargs):
            return BytesIO(content) if title == '导入桨叶几何表 CSV/TXT' else None
        with patch('streamlit.file_uploader', side_effect=upload):
            app.run()
            field(app.button,'应用桨叶几何表导入').click().run()
            ok(app)
        assert app.session_state['module-draft']['assets']['geometry.csv'] == changed['assets']['geometry.csv']
        content = content.replace(b'0.105',b'NaN',1)
        if content == export_table(pd.read_csv(BytesIO(changed['assets']['geometry.csv'])),'中文导入验证'):
            content = b'r_over_R,chord_m,twist_deg\n.2,NaN,10\n1,.065,-4\n'
        before_bad = deepcopy(app.session_state['module-draft'])
        with patch('streamlit.file_uploader', side_effect=upload):
            app.run()
            ok(app)
            assert any('原表保留' in value.value for value in app.error)
        assert app.session_state['module-draft'] == before_bad
        app.run()
        field(app.number_input,'径向叶素数').set_value(24).run()
        field(app.number_input,'方位离散数').set_value(12).run()
        field(app.radio,'求解任务').set_value('批量性能扫描').run()
        field(app.selectbox,'点列生成方式1').set_value('步长').run()
        field(app.number_input,'起点1').set_value(12.).run()
        field(app.number_input,'终点1').set_value(13.).run()
        field(app.number_input,'步长1').set_value(.5).run()
        field(app.button,'运行旋翼计算').click().run()
        ok(app)
        record = deepcopy(app.session_state['module-result'])
        assert record['answer']['status'] == 'converged',record['answer']
        assert app.session_state['module-draft']['sweep']['axes']['collective_deg'] == [12.,12.5,13.]
        field(app.number_input,'步长1').set_value(0.).run()
        ok(app)
        assert field(app.button,'运行旋翼计算').disabled
        assert app.session_state['module-result'] == record
        field(app.number_input,'步长1').set_value(.5).run()
        field(app.button,'保存旋翼算例').click().run()
        saved = deepcopy(app.session_state['module-draft'])
        field(app.button,'重新打开旋翼算例').click().run()
        assert app.session_state['module-draft'] == saved
        field(app.radio,'工作区').set_value('全机配平').run()
        assert app.session_state['design']['aircraft']['name'] == '千机-200轻型无人直升机'
        field(app.selectbox,'配平任务').set_value('速度曲线').run()
        field(app.selectbox,'速度扫描 / (m/s)输入方式').set_value('起点/终点/步长').run()
        field(app.number_input,'速度扫描 / (m/s)终点').set_value(5.).run()
        field(app.number_input,'速度扫描 / (m/s)步长').set_value(5.).run()
        field(app.number_input,'每桨径向叶素数').set_value(24).run()
        field(app.number_input,'整周方位角站数').set_value(12).run()
        field(app.button,'运行分析').click().run()
        ok(app)
        record = deepcopy(app.session_state['workspace-result'])
        assert record['answer']['summary']['total'] == 2
        replay(record)
        field(app.radio,'工作区').set_value('悬停求解').run()
        field(app.selectbox,'预算任务').set_value('主桨尺寸—转速图').run()
        modes = [item for item in app.selectbox if item.label.endswith('（逗号分隔）输入方式')]
        assert len(modes) == 2
        modes[0].set_value('起点/终点/步长').run()
        field(app.number_input,'每桨径向叶素数').set_value(24).run()
        field(app.button,'运行分析').click().run()
        ok(app)
        assert app.session_state['workspace-result']['answer']['summary']['total'] == 4
        field(app.radio,'工作区').set_value('全机配平').run()
        from rotordesignlab.comparison_ui import LABEL
        from rotordesignlab.comparison_tables import export_candidates
        items = [dict(name=f'中文表方案{i+1}', main_radius_m=1.1, main_rpm=1700.-i*30,
                      tail_radius_m=.24, tail_arm_m=1.7, cg_x_m=0., geometry_rule='preserve_chord',
                      provenance='候选表导入检查：工程假设') for i in range(3)]
        content = export_candidates(items)
        field(app.selectbox,'配平任务').set_value(LABEL).run()
        with patch('streamlit.file_uploader', side_effect=lambda title,*a,**kw: BytesIO(content) if title=='导入三方案参数 CSV/TXT' else None):
            app.run()
            field(app.button,'应用三方案参数导入').click().run()
            ok(app)
        assert field(app.text_input,'候选1名称').value == '中文表方案1'
        field(app.button,'运行分析').click().run()
        ok(app)
        comparison = app.session_state['workspace-result']
        assert comparison['answer']['status'] == 'converged'
        replay(comparison)
        field(app.radio,'工作区').set_value('孤立旋翼').run()
        field(app.checkbox,'允许替换当前旋翼草稿').check().run()
        field(app.selectbox,'旋翼起始模板').set_value('UH-60 公开基准旋翼').run()
        field(app.button,'从旋翼模板新建').click().run()
        field(app.selectbox,'旋翼参数分组').set_value('几何与翼型数据表').run()
        grid = json.loads(app.session_state['module-draft']['assets']['polar.json'])
        section = grid['sections'][0]
        layer = section.get('reynolds_slices',[section])[0]['cl']
        frame = pd.DataFrame([[a,*v] for a,v in zip(layer['alpha_deg'],layer['values'])],
                             columns=['alpha_deg']+[f'Ma={m:g}' for m in layer['mach']])
        content = export_table(frame,'公共翼型分层往返检查')
        with patch('streamlit.file_uploader', side_effect=lambda title,*a,**kw: BytesIO(content) if title=='导入当前翼型数据层 CSV/TXT' else None):
            app.run()
            field(app.button,'应用当前翼型数据层导入').click().run()
            ok(app)
        after = json.loads(app.session_state['module-draft']['assets']['polar.json'])
        assert after['sections'] == grid['sections'], 'Re/Mach网格或高攻角分支改变'
        print('C2网页：几何应用、中文表导入/失败保护、步长、保存重开、千机命名及整机CLI复算通过')


if __name__ == '__main__':
    main()
