"""Assembly owns installation and airframe settings; analyses read snapshots."""
from copy import deepcopy
from hashlib import sha256
import json

import numpy as np
import pandas as pd
import streamlit as st

from . import assembly, designs, module_workspace, rotor_module
from .design_ui import current, replace_design, details


def ensure_design():
    if 'design' not in st.session_state:
        replace_design(assembly.from_legacy(designs.from_template(next(iter(designs.TEMPLATES)))))


def update_design(value):
    # Keep library identity and every submitted result; editing creates a dirty draft.
    st.session_state['design'] = value
    st.session_state['design_epoch'] += 1
    st.session_state['table_bases'] = {}


def installation_editor(index):
    design = current()
    instance = design['assembly']['instances'][index]
    installation = instance['installation']
    rotor = design['aircraft']['rotors'][index]
    role = installation['role']
    prefix = f'install:{st.session_state["design_epoch"]}:{index}:'
    st.caption('机体系X向前、Y向右、Z向下。桨毂位置和整机重心采用同一原点；求解时统一移轴。')
    drive_mode = 'given'
    if role == 'tail':
        drive_mode = st.selectbox('尾桨转速定义', ['given', 'main_ratio'],
                                  index=0 if instance['drive']['rpm_mode'] == 'given' else 1,
                                  key=prefix+'drive-mode',
                                  format_func=lambda v: '独立给定转速' if v == 'given' else '按主桨转速比联动',
                                  help='选择后显示对应输入，点击应用后才修改装配；联动转速为主桨转速乘速比。')
    with st.form(prefix+'position-drive'):
        position = [col.number_input('桨毂位置 ' + axis + ' / m', value=float(value), help='相对机型原点的坐标，正方向按机体系。')
                    for col, axis, value in zip(st.columns(3), 'xyz', installation['position_m'])]
        rpm = installation['defaults']['rpm']
        ratio = None
        if drive_mode == 'given':
            rpm = st.number_input('安装参考转速 / r/min', value=float(rpm),
                                  help='给定的整机工作转速；主桨转速还用于尾桨速比联动。')
        else:
            main_rpm = next(r['defaults']['rpm'] for r in design['aircraft']['rotors'] if r['role'] == 'main')
            ratio = st.number_input('尾桨/主桨转速比', value=float(instance['drive'].get('ratio', rpm/main_rpm)),
                                    help='正数；尾桨转速由主桨转速乘本值计算，旋向由旋翼模块定义。')
        collective = st.number_input('配平总距初值 / °', value=float(installation['defaults']['collective_deg']),
                                    help='整机配平和反求的初值，不是整机已配平的总距；求解结果会重新给出。')
        efficiency = st.number_input('该旋翼传动效率', value=float(installation['transmission_efficiency']),
                                    help='轴端需用功率除以该效率得到动力接口需求，0<η≤1。主尾桨分别记账，不再叠加隐含全局效率。')
        with st.expander('来源与备注（可选）'):
            note = st.text_input('安装与传动参数来源', value=installation.get('provenance', '待补充安装资料'),
                                 help='继承已有来源，可补充说明；修改值需要重新核对依据。')
        if st.form_submit_button('应用位置与传动设置'):
            candidate = deepcopy(design)
            target = candidate['assembly']['instances'][index]
            target['installation'].update(position_m=position, transmission_efficiency=efficiency, provenance=note)
            target['installation']['defaults'].update(rpm=rpm, collective_deg=collective)
            target['drive'] = dict(connection='powerplant', rpm_mode=drive_mode)
            if drive_mode == 'main_ratio':
                target['drive']['ratio'] = ratio
            try:
                assembly.refresh(candidate)
                assembly.validate(candidate)
                update_design(candidate)
                st.rerun()
            except (ValueError, KeyError, TypeError) as error:
                st.error('安装定义无效，原草稿保留：' + str(error))
    st.caption(f"实际整机工作转速：{rotor['defaults']['rpm']:.7g} r/min；传动连接：共用轴功率接口。")
    st.caption('旋向属于旋翼模块，在此只读。操纵直接定义为桨叶变距角；θ=θ₀+θc cosψ+θs sinψ，ψ从局部+x朝+y几何增大，旋向决定桨叶经过的时间次序。')
    from .mounting_ui import render_mounting
    def write_installation(path, value):
        target = current()['assembly']['instances'][index]['installation']
        for name in path[3:-1]:
            target = target[name]
        target[path[-1]] = value
        assembly.refresh(current())
    render_mounting(rotor, index, st.session_state['design_epoch'], write_installation, allow_rotation_edit=False)


def module_selector(index):
    instance = current()['assembly']['instances'][index]
    saved = instance['snapshot']
    st.write('当前模块：' + saved['module']['name'])
    st.caption('固定快照 SHA-256：' + saved['sha256'])
    st.caption('模块库更新不会自动替换此快照。换入模块保留安装位置、方向、传动及配平初值；不会采用孤立工况中的总距、来流或空气环境。')
    prefix = f'bind:{st.session_state["design_epoch"]}:{index}'
    rows = dict(module_workspace.saved())
    identifier = None
    if rows:
        identifier = st.selectbox('本机旋翼方案', list(rows), index=0,
                              format_func=lambda value: rows[value]+' · '+value[:8], key=prefix+'library',
                              help='只嵌入所选算例的旋翼本体。角色由当前安装位决定，模块自身没有主尾桨角色。')
    if st.button('装入所选旋翼方案', key=prefix+'bind', disabled=identifier is None):
        try:
            draft, revision = module_workspace.load(identifier)
            result = assembly.install(current(), index, draft['module'], draft['assets'],
                                      dict(kind='module_library', identifier=identifier, revision_sha256=revision,
                                           module_case_sha256=module_workspace.digest(draft)))
            update_design(result)
            st.rerun()
        except (ValueError, OSError, KeyError, TypeError) as error:
            st.error('加载失败，当前装配保留：' + str(error))
    upload = st.file_uploader('旋翼方案文件', type=['rdlr', 'rdlc'], key=prefix+'upload',
                              help='加载孤立旋翼导出的同一方案文件；只取旋翼本体，工况和试验姿态不带入整机。')
    if st.button('装入所选旋翼文件', key=prefix+'file', disabled=upload is None):
        try:
            data = upload.getvalue()
            if upload.name.lower().endswith('.rdlc'):
                draft = module_workspace.unpack(data)
                module, assets = draft['module'], draft['assets']
            else:
                module, assets = rotor_module.unpack(data)
            update_design(assembly.install(current(), index, module, assets,
                                           dict(kind='uploaded_module', package_sha256=sha256(data).hexdigest())))
            st.rerun()
        except (ValueError, OSError, KeyError, TypeError) as error:
            st.error('加载失败，当前装配保留：' + str(error))
    with st.expander('模块资料、缺项及独立编辑'):
        st.write('来源记录', instance['source'])
        st.write('旋翼资料来源：' + saved['module']['provenance'])
        mass = saved['module']['blade_mass']
        hub = saved['module']['hub']
        st.caption('单片质量 / kg：' + str(mass.get('mass_kg', '未提供')) + '；桨毂质量 / kg：' + str(hub.get('mass_kg', '未提供')))
        st.caption('单片质量、桨毂及完整质量矩保存在快照中。历史模型沿用原总质量；新耦合模型按下方质量参考构型分账，不重复累加。')
        module, assets = assembly.module_data(instance)
        st.download_button('下载此安装位的旋翼模块', rotor_module.pack(module, assets), 'installed-rotor.rdlr', key=prefix+'download')
        if st.button('到孤立旋翼工作区编辑副本', key=prefix+'edit'):
            from . import module_ui
            rotor = current()['aircraft']['rotors'][index]
            case = dict(schema_version=4, model='rotor_module', module_file='module.rdlr', method='spatial',
                        flapping_model='module', **rotor['defaults'], flow_rotor_m_s=[0., 0., 0.],
                        gravity_rotor_m_s2=(assembly.selected_basis(rotor).T @ np.array([0., 0., 9.80665])).tolist(),
                        environment={'mode': 'isa', 'isa_temperature_offset_k': 0.}, altitude_m=0.)
            draft = dict(module=module, assets=assets, case=case, sweep=None)
            changed = 'module-draft' in st.session_state and module_ui.fingerprint() != st.session_state.get('module-saved-digest')
            if changed:
                st.session_state['module-pending'] = (draft, None, None, None)
            else:
                module_ui.replace(draft)
            st.session_state['pending-workspace'] = '孤立旋翼'
            st.rerun()



def render():
    from .aircraft_manager_ui import render as scheme_manager
    if not scheme_manager():
        return
    st.subheader('整机装配')
    if current().get('format_version') != 2:
        st.info('这是旧版整机方案。可保持原格式复算；转换会生成新装配草稿和模块快照，保留原文件。')
        if st.button('将当前方案另存为模块化装配草稿'):
            try:
                replace_design(assembly.from_legacy(current()))
                st.rerun()
            except (ValueError, KeyError, TypeError) as error:
                st.error(str(error))
        details()
        return
    st.info('当前支持一副主旋翼＋一副尾桨，共用轴功率接口。旋翼本体从模块加载；本页设置安装和机体，其余分析页只填写本次工况。')
    st.dataframe(pd.DataFrame(assembly.describe(current())), hide_index=True)
    slots = current()['assembly']['instances']
    index = st.selectbox('选择安装位与角色', range(len(slots)),
                         format_func=lambda i: ('主旋翼' if slots[i]['installation']['role'] == 'main' else '尾桨')+' · '+slots[i]['installation']['id'],
                         help='将任何独立旋翼模块装入选中的角色；同一模块可形成两个独立安装实例。')
    with st.expander('加载或替换旋翼模块', expanded=True):
        module_selector(index)
    with st.expander('安装位置、方向、操纵与传动', expanded=True):
        installation_editor(index)
    details(assembly_only=True)
    from .coupling_ui import render as render_coupling
    render_coupling()
    errors = designs.issues(current())
    if errors:
        st.warning('装配尚未满足输入要求，草稿保留；请修正后计算或保存。')
        for error in errors:
            st.error(error)
    if st.button('检查整机装配'):
        if not errors:
            st.success('快照、安装和基本参数检查通过。各分析所需的额外资料及数据域在相应入口继续检查。')
        for analysis, name in [('hover_budget', '悬停预算'), ('trim', '六分量配平'), ('linearize', '开环诊断')]:
            missing = designs.issues(current(), analysis)
            st.write(name + '：' + ('；'.join(missing) if missing else '所需输入齐备'))


def analysis_header():
    from .aircraft_manager_ui import render as scheme_manager
    if not scheme_manager():
        return False
    st.caption('分析页读取当前整机装配；部件、安装、质量和动力请在整机装配修改。各任务工况分别保存。')
    with st.expander('查看当前装配快照'):
        if current().get('format_version') == 2:
            st.dataframe(pd.DataFrame(assembly.describe(current())), hide_index=True)
        else:
            st.caption('旧格式方案按原语义复算，尚未转换为模块化装配。')
        st.caption('整机总质量 / kg：'+str(current()['aircraft']['mass_properties']['mass_kg']))
    return True
