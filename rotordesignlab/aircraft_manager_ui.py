"""Shared aircraft scheme actions for assembly and all aircraft analyses."""
from copy import deepcopy
from pathlib import Path
import streamlit as st
from . import designs, assembly


def render():
    from .assembly_ui import ensure_design
    from .design_ui import current, replace_design, dirty, key_for, put_at
    ensure_design()

    def save(copy=False):
        identifier, revision = designs.save_design(
            current(), None if copy else st.session_state.get('design_id'),
            None if copy else st.session_state.get('design_version'))
        st.session_state.update(design_id=identifier, design_version=revision,
                                saved_fingerprint=designs.digest(current()))

    def adopt(design, identifier=None, revision=None, baseline=None):
        if dirty():
            st.session_state['aircraft-pending'] = (deepcopy(design), identifier, revision, baseline)
            st.rerun()
        replace_design(design, identifier, revision)
        if baseline is not None:
            st.session_state['saved_fingerprint'] = baseline
        st.rerun()

    widget = key_for(['aircraft', 'name'])
    def rename():
        put_at(['aircraft', 'name'], st.session_state[widget])
    st.text_input('整机方案名称', current()['aircraft']['name'], key=widget, on_change=rename,
                  help='四个整机入口共用此方案及各自工况；旋翼方案独立保存。')
    if st.session_state.pop('aircraft-save-notice', False):
        st.success('已保存到本机方案库。')
    if 'aircraft-pending' in st.session_state:
        st.warning('当前整机方案有未保存修改，请选择后再替换。')
        choice = st.radio('处理未保存修改', ['取消', '保存后继续', '放弃修改并继续'], key='aircraft-pending-choice')
        if st.button('确认选择'):
            try:
                if choice != '取消':
                    if choice == '保存后继续':
                        save()
                    design, identifier, revision, baseline = st.session_state['aircraft-pending']
                    if identifier == st.session_state.get('design_id'):
                        revision = st.session_state.get('design_version')
                        if choice == '保存后继续':
                            if baseline is None:
                                # Reopening this scheme must read the just-saved head;
                                # an explicit history restore keeps its selected snapshot.
                                design, revision = designs.load_design(identifier)
                            else:
                                baseline = designs.digest(current())
                    replace_design(design, identifier, revision)
                    if baseline is not None:
                        st.session_state['saved_fingerprint'] = baseline
                st.session_state.pop('aircraft-pending')
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
        return False
    columns = st.columns(4)
    with columns[0].popover('新建'):
        templates = [name for name in designs.TEMPLATES if '兼容旧版' not in name]
        selected = st.selectbox('整机起始模板', templates, help='来源和工程估计随方案保存；旧格式仍可通过打开读取。')
        if st.button('创建整机方案'):
            adopt(assembly.from_legacy(designs.from_template(selected)))
    with columns[1].popover('打开'):
        names = dict(designs.saved_designs())
        if names:
            selected = st.selectbox('本机整机方案', list(names), format_func=lambda i: names[i]+' · '+i[:8])
            if st.button('打开所选方案'):
                try:
                    design, revision = designs.load_design(selected)
                    adopt(design, selected, revision)
                except (ValueError, OSError) as error:
                    st.error(str(error))
        else:
            st.caption('本机尚无已保存整机方案，可新建或打开方案文件。')
        upload = st.file_uploader('整机方案文件', type=['rdl'])
        if st.button('打开方案文件', disabled=upload is None):
            try:
                adopt(designs.unpack(upload.getvalue()))
            except (ValueError, OSError) as error:
                st.error('导入失败，草稿已保留：'+str(error))
    if columns[2].button('保存', type='primary'):
        try:
            save()
            st.session_state['aircraft-save-notice'] = True
            st.rerun()
        except (ValueError, OSError) as error:
            st.error(str(error))
    with columns[3].popover('更多'):
        if st.button('复制方案'):
            try:
                save(copy=True)
                st.session_state['aircraft-save-notice'] = True
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
        try:
            st.download_button('导出方案文件', designs.pack(current()), 'aircraft-scheme.rdl')
        except ValueError as error:
            st.caption('请先修正参数：'+str(error))
        identifier = st.session_state.get('design_id')
        if identifier:
            histories = sorted((Path(designs.LIBRARY)/'history').glob(identifier+'-*.rdl'), key=lambda p: p.stat().st_mtime, reverse=True)
            if histories:
                revision = st.selectbox('历史版本', histories, format_func=lambda p: p.stem[-64:-52])
                if st.button('恢复历史到草稿'):
                    try:
                        head, version = designs.load_design(identifier)
                        adopt(designs.unpack(revision.read_bytes()), identifier, version, designs.digest(head))
                    except (ValueError, OSError) as error:
                        st.error(str(error))
            if st.button('将已保存版本移入回收区'):
                try:
                    from .aircraft_library import trash
                    trash(identifier, st.session_state['design_version'])
                    st.session_state.update(design_id=None, design_version=None, saved_fingerprint=None)
                    st.rerun()
                except (ValueError, OSError) as error:
                    st.error(str(error))
        from .aircraft_library import deleted, restore
        deleted_names = dict(deleted())
        if deleted_names:
            selected = st.selectbox('回收区方案', list(deleted_names), format_func=lambda value: deleted_names[value]+' · '+value[:8])
            if st.button('恢复为副本'):
                try:
                    restore(selected)
                    st.session_state['aircraft-save-notice'] = True
                    st.rerun()
                except (ValueError, OSError) as error:
                    st.error(str(error))
    identifier = st.session_state.get('design_id')
    st.caption('方案编号：'+(identifier[:8] if identifier else '尚未保存')+'；'+('有未保存修改' if dirty() else '已保存')+'。各分析结果绑定实际运行输入。')
    return True
