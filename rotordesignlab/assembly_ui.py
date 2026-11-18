"""Assembly owns installation and airframe settings; analyses read snapshots."""
from copy import deepcopy
from hashlib import sha256
import json

import numpy as np
import pandas as pd
import streamlit as st

from . import assembly, designs, module_workspace, rotor_module
from .design_ui import current, replace_design, manager, details, dirty


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
    with st.form(prefix+'position-drive'):
        position = [col.number_input('桨毂位置 ' + axis + ' / m', value=float(value), help='相对机型原点的坐标，正方向按机体系。')
                    for col, axis, value in zip(st.columns(3), 'xyz', installation['position_m'])]
        drive_mode = 'given'
        if role == 'tail':
            drive_mode = st.selectbox('尾桨转速定义', ['given', 'main_ratio'],
                                      index=0 if instance['drive']['rpm_mode'] == 'given' else 1,
                                      format_func=lambda v: '独立给定转速' if v == 'given' else '按主桨转速比联动',
                                      help='联动模式：尾桨转速=主桨参考转速×速比；不会把孤立算例中的转速自动当作整机工作转速。')
        # Both fields stay visible in the form; only the selected definition applies.
        rpm = st.number_input('安装参考转速 / r/min', value=float(installation['defaults']['rpm']),
                              help='给定转速模式的工作转速；主桨此值还用于尾桨速比联动。应位于模块转速限制内。')
        ratio = None
        if role == 'tail':
            main_rpm = next(r['defaults']['rpm'] for r in design['aircraft']['rotors'] if r['role'] == 'main')
            ratio = st.number_input('尾桨/主桨转速比', value=float(instance['drive'].get('ratio', rotor['defaults']['rpm']/main_rpm)),
                                    help='仅联动模式使用；给定转速模式不保存此输入。正数，转速大小之比，旋向由模块定义。')
        collective = st.number_input('配平总距初值 / °', value=float(installation['defaults']['collective_deg']),
                                    help='整机配平和反求的初值，不是整机已配平的总距；求解结果会重新给出。')
        efficiency = st.number_input('该旋翼传动效率', value=float(installation['transmission_efficiency']),
                                    help='轴端需用功率除以该效率得到动力接口需求，0<η≤1。主尾桨分别记账，不再叠加隐含全局效率。')
        note = st.text_input('安装与传动参数来源', value=installation.get('provenance', '待补充安装资料'),
                             help='说明安装尺寸、参考转速、速比、效率的资料来源或工程估计。')
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
    identifier = st.selectbox('从模块库选择旋翼算例', list(rows), index=0 if rows else None,
                              format_func=lambda value: rows[value]+' · '+value[:8], key=prefix+'library',
                              help='只嵌入所选算例的旋翼本体。角色由当前安装位决定，模块自身没有主尾桨角色。')
    if st.button('将库中模块装入此安装位', key=prefix+'bind', disabled=identifier is None):
        try:
            draft, revision = module_workspace.load(identifier)
            result = assembly.install(current(), index, draft['module'], draft['assets'],
                                      dict(kind='module_library', identifier=identifier, revision_sha256=revision,
                                           module_case_sha256=module_workspace.digest(draft)))
            update_design(result)
            st.rerun()
        except (ValueError, OSError, KeyError, TypeError) as error:
            st.error('加载失败，当前装配保留：' + str(error))
    upload = st.file_uploader('从文件加载旋翼模块或算例', type=['rdlr', 'rdlc'], key=prefix+'upload',
                              help='模块包和算例包均可；副本嵌入整机，不依赖外部路径。')
    if st.button('将文件中模块装入此安装位', key=prefix+'file', disabled=upload is None):
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
        consent = st.checkbox('允许替换孤立旋翼工作区草稿', key=prefix+'consent', help='将装配中的副本载入孤立工作区。编辑和保存后，仍需回到装配页显式换入。')
        if st.button('到孤立旋翼工作区编辑副本', key=prefix+'edit'):
            from . import module_ui
            exists = 'module-draft' in st.session_state
            changed = exists and module_ui.fingerprint() != st.session_state.get('module-saved-digest')
            if changed and not consent:
                st.warning('孤立旋翼有未保存草稿，请先保存或勾选允许替换。')
            else:
                rotor = current()['aircraft']['rotors'][index]
                case = dict(schema_version=4, model='rotor_module', module_file='module.rdlr', method='spatial',
                            flapping_model='module', **rotor['defaults'], flow_rotor_m_s=[0., 0., 0.],
                            gravity_rotor_m_s2=(assembly.selected_basis(rotor).T @ np.array([0., 0., 9.80665])).tolist(),
                            environment={'mode': 'isa', 'isa_temperature_offset_k': 0.}, altitude_m=0.)
                module_ui.replace(dict(module=module, assets=assets, case=case, sweep=None))
                st.session_state['pending-workspace'] = '孤立旋翼'
                st.rerun()


def render():
    manager(assembly_mode=True)
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
    ensure_design()
    st.subheader('当前整机：' + current()['aircraft']['name'])
    st.caption('分析页读取当前装配快照。修改部件、安装、机体质量和动力请进入“整机装配”。本页只设置本次分析工况。')
    if dirty():
        st.caption('正在使用未保存的整机草稿；运行时仍保存实际输入快照。')
    with st.expander('读取已保存装配、保存工况与查看快照'):
        rows = dict(designs.saved_designs())
        identifier = st.selectbox('读取整机方案', list(rows), index=0 if rows else None,
                                  format_func=lambda value: rows[value]+' · '+value[:8], help='旧方案可按原语义复算；模块化装配包含固定模块快照。')
        consent = st.checkbox('允许替换当前整机草稿', help='有未保存的装配或工况修改时，先保存或勾选后再读取其他方案。')
        if st.button('读取所选整机', disabled=identifier is None):
            if dirty() and not consent:
                st.warning('当前整机草稿尚未保存。')
            else:
                try:
                    design, version = designs.load_design(identifier)
                    replace_design(design, identifier, version)
                    st.rerun()
                except (ValueError, OSError) as error:
                    st.error(str(error))
        if st.button('保存整机与当前工况'):
            try:
                identifier, version = designs.save_design(current(), st.session_state.get('design_id'), st.session_state.get('design_version'))
                st.session_state.update(design_id=identifier, design_version=version, saved_fingerprint=designs.digest(current()))
                st.success('整机与工况已保存。')
            except (ValueError, OSError) as error:
                st.error(str(error))
        if current().get('format_version') == 2:
            st.dataframe(pd.DataFrame(assembly.describe(current())), hide_index=True)
        else:
            st.caption('旧版兼容方案，尚未转换为模块化装配；数值定义保持原文件。')
        st.caption('整机总质量 / kg：' + str(current()['aircraft']['mass_properties']['mass_kg']))
