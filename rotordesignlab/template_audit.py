"""Trace template parameters to repository sources without altering inputs."""
from hashlib import sha256
import json
from pathlib import Path
from . import designs, module_workspace

ROOT = Path(__file__).resolve().parents[1]
NOTES = {
    '千机-200轻型无人直升机': ('工程估计演示模板', '总体设计流程、固定质量参数敏感性和软件复算',
        '几何、翼型、质量惯量、机身尾翼、动力曲线均含工程估计；不是实测机型。尺寸变化后的结构重量另核。'),
    'UH-60 公开部件模型（含工程估计）': ('公开模型转录＋工程假设', '公开部件与模型互校、方法差异分析',
        '公开几何/系数不等于整机验证。尾桨一阶质量矩、下洗、冻结平尾控制和动力额定含估算；T700真实可用功率未接入。R19开环限制保持。'),
    '三桨叶孤立旋翼示例（兼容旧版）': ('历史估算模板', '旧格式复算与接口兼容',
        '保留原参数语义；新建独立旋翼优先使用模块入口。不提供完整整机验证依据。'),
    '千机-200轻型无人直升机（A2质量分账，试验性）': ('构造的质量分账检查模板', '质量归属和隐式耦合数值检查',
        '桨叶/桨毂质量矩与整机惯量为一致性构造，不是测量数据。R19未关闭，仅作开环故障诊断。'),
    '合成三桨叶旋翼（工程估计）': ('独立旋翼估算模板', '旋翼配置、几何/气动敏感性、保存复算',
        '单片质量与桨毂属性仍有缺项；不得从已有一阶/二阶矩反推真实质量。'),
    'UH-60 公开基准旋翼': ('从公开部件模板提取的旋翼', '坐标/载荷与旧算例同输入对照',
        '使用公开主桨模型气动表；不是独立旋翼实测全域验证。Re、斜流修正和非定常失速覆盖有限。'),
}


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, prefix+'/'+key)
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        for index,item in enumerate(value):
            yield from leaves(item,prefix+'/'+str(index))
    else:
        yield prefix, value


def source_for(name, path):
    if path.rsplit('/',1)[-1] in ('schema_version','kind','id','name','description','units','axes','provenance'):
        return '标识/原来源文字', '原文件原值记录；该文字本身不构成独立验证'
    if 'UH-60' not in name:
        if 'A2' in name:
            return '工程构造/模型设定', 'tools/build_a2_example.py；基础气动继承千机-200估算输入'
        return '工程估计/模型设定', 'examples/synthetic-aircraft.json；tools/prepare_hover_templates.py；tools/prepare_trim_templates.py'
    main = path.startswith('/rotors/0/') or path.startswith('/rotor/')
    tail = path.startswith('/rotors/1/')
    field = path.rsplit('/',1)[-1]
    if path.startswith('/mass_properties/'):
        return '公开数学模型转录', 'tools/prepare_public_helicopter.py 引用 NASA TM-85890 Table 1；含坐标/惯量积符号转换，同配置旋翼分账仍缺'
    if '/powerplant/' in path or 'transmission_efficiency' in path or '/limits/' in path:
        return '工程估计/设计限位', 'tools/prepare_hover_templates.py；动力曲线为演示值，不是T700额定'
    if field == 'polar_json':
        return ('公开表转录＋分段处理' if main else '公开翼型＋Re工程估计'), 'tools/prepare_public_helicopter.py；validation/aero-upgrade，按表内provenance核对，不视为实测全域'
    if (path.startswith('/flapping/') and field in ('inertia_kg_m2','first_mass_moment_kg_m','hinge_offset_m')) or (main and (field in ('blade_count','radius_m','geometry_csv','rpm','position_m','thrust_axis_body',
                           'inertia_kg_m2','first_mass_moment_kg_m','hinge_offset_m') or path.startswith('/blade_mass/'))):
        return '公开原模型转录/单位转换', 'src/H60_constants.jl；tools/prepare_hover_templates.py；tools/prepare_trim_templates.py；单片质量缺项仍保留'
    if tail and field in ('blade_count','radius_m','geometry_csv','rpm','position_m','thrust_axis_body','inertia_kg_m2','delta3_deg'):
        return '公开原模型转录/单位转换', 'src/H60_constants.jl；tools/prepare_public_helicopter.py；尾桨根切0.2R仍属估计'
    if '/wind_tables/' in path:
        return '公开原模型气动表转录', 'data/H60fuselage.mat；tools/prepare_public_helicopter.py，ft²/ft³转SI及风轴符号'
    if '/surfaces/' in path and field in ('position_m','area_m2','angle_deg','cl','cd','pressure_ratio','wake_fraction','tail_wake_fraction'):
        return '公开模型参数/表格转录', 'src/H60_constants.jl；tools/prepare_public_helicopter.py 引用TM-85890；下洗为模型系数'
    return '模型约定/工程假设', 'tools/prepare_public_helicopter.py；冻结平尾控制、反向来流对称延拓及未列公开来源的值保留为假设'


def audit():
    rows, templates = [], []
    sources = list(designs.TEMPLATES.items())+[(name,ROOT/'examples/rotor-modules'/folder/'module.json')
                                             for name,folder in module_workspace.TEMPLATES.items()]
    for name,path in sources:
        raw = json.loads(path.read_text(encoding='utf-8-sig'))
        hashes = {path.relative_to(ROOT).as_posix():sha256(path.read_bytes()).hexdigest()}
        for pointer,value in leaves(raw):
            category, source = source_for(name,pointer)
            rows.append(dict(template=name,parameter=pointer,value=value,classification=category,source=source))
            if pointer.rsplit('/',1)[-1] in ('geometry_csv','polar_csv','polar_json'):
                asset = (path.parent/value).resolve()
                hashes[asset.relative_to(ROOT).as_posix()] = sha256(asset.read_bytes()).hexdigest()
        templates.append(dict(name=name,classification=NOTES[name][0],use=NOTES[name][1],limitations=NOTES[name][2],
                              input_sha256=hashes,parameter_count=sum(row['template']==name for row in rows)))
    return dict(schema_version=1, scope='仓库来源链与假设审核；不是新增试验验证或原报告全部逐页复核',
                templates=templates,parameters=rows)


def panel():
    import streamlit as st
    with st.sidebar.expander('模板来源与适用范围'):
        name = st.selectbox('查看起始模板依据',list(NOTES))
        classification, use, limits = NOTES[name]
        st.caption(classification)
        st.write('用途：'+use)
        st.write(limits)
        st.caption('这里说明起始模板；用户修改后的参数仍需填写自己的来源。详细清单见使用说明中的模板审核。')
