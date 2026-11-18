"""User-facing scheme actions; persistence remains in module_workspace."""
from copy import deepcopy
import numpy as np
import streamlit as st
from . import module_workspace as store, rotor_module


def new_scheme(name):
    draft = store.template(name)
    for limit in ('power_w', 'torque_nm'):
        draft['module']['rotor']['limits'].pop(limit, None)
    return draft


def render():
    from .module_ui import current, field, key, replace, fingerprint

    def save(fresh=False):
        identifier, version = store.save(
            current(), None if fresh else st.session_state.get('module-id'),
            None if fresh else st.session_state.get('module-version'))
        st.session_state.update({'module-id': identifier, 'module-version': version,
                                 'module-saved-digest': store.digest(current())})

    def adopt(draft, identifier=None, version=None, baseline=None):
        if fingerprint() != st.session_state['module-saved-digest']:
            st.session_state['module-pending'] = (deepcopy(draft), identifier, version, baseline)
            st.rerun()
        replace(draft, identifier, version)
        if baseline is not None:
            st.session_state['module-saved-digest'] = baseline
        st.rerun()

    field(current()['module'], 'name', '旋翼方案名称', prefix='module', help='保存到本机方案库；导出方案文件可分享或换电脑继续计算。')
    if st.session_state.pop('module-save-notice', False):
        st.success('已保存到本机方案库。')
    if 'module-pending' in st.session_state:
        st.warning('当前方案有未保存修改，请选择后再替换。')
        choice = st.radio('处理未保存修改', ['取消', '保存后继续', '放弃修改并继续'], key=key('pending-choice'))
        if st.button('确认选择'):
            try:
                if choice != '取消':
                    if choice == '保存后继续':
                        save()
                    draft, identifier, version, baseline = st.session_state['module-pending']
                    # Saving the current scheme may advance the selected head.
                    if identifier == st.session_state.get('module-id'):
                        version = st.session_state.get('module-version')
                        if choice == '保存后继续':
                            baseline = store.digest(current())
                    replace(draft, identifier, version)
                    if baseline is not None:
                        st.session_state['module-saved-digest'] = baseline
                st.session_state.pop('module-pending')
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
        return

    columns = st.columns(4)
    with columns[0].popover('新建'):
        template = st.selectbox('旋翼起始模板', list(store.TEMPLATES), key=key('template'), help='模板来源随方案保留；新方案的功率和扭矩上限默认不启用。')
        if st.button('创建旋翼方案'):
            adopt(new_scheme(template))
    with columns[1].popover('打开'):
        names = dict(store.saved())
        if names:
            selected = st.selectbox('本机旋翼方案', list(names), format_func=lambda i: names[i]+' · '+i[:8])
            if st.button('打开所选方案'):
                try:
                    draft, version = store.load(selected)
                    adopt(draft, selected, version)
                except (ValueError, OSError) as error:
                    st.error(str(error))
        else:
            st.caption('本机尚无已保存方案。可新建或打开方案文件。')
        upload = st.file_uploader('旋翼方案文件', type=['rdlc', 'rdlr'], key=key('module-upload'), help='同一方案文件也可直接载入整机装配。')
        if st.button('打开方案文件', disabled=upload is None):
            try:
                if upload.name.lower().endswith('.rdlc'):
                    draft = store.unpack(upload.getvalue())
                else:
                    module, assets = rotor_module.unpack(upload.getvalue())
                    case = deepcopy(store.template(next(iter(store.TEMPLATES)))['case'])
                    for name in ('rpm', 'collective_deg'):
                        case[name] = float(np.mean(module['rotor']['limits'][name]))
                    draft = dict(module=module, assets=assets, case=case, sweep=None)
                adopt(draft)
            except (ValueError, OSError, TypeError) as error:
                st.error('导入失败，草稿已保留：'+str(error))
    if columns[2].button('保存', type='primary'):
        try:
            save()
            st.session_state['module-save-notice'] = True
            st.rerun()
        except (ValueError, OSError) as error:
            st.error(str(error))
    with columns[3].popover('更多'):
        if st.button('复制方案'):
            try:
                save(fresh=True)
                st.session_state['module-save-notice'] = True
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
        try:
            st.download_button('导出方案文件', store.pack(current()), 'rotor-scheme.rdlc')
        except (ValueError, TypeError) as error:
            st.warning('请先修正参数：'+str(error))
        identifier = st.session_state.get('module-id')
        if identifier:
            history = store.revisions(identifier)
            if history:
                revision = st.selectbox('历史版本', history, format_func=lambda v: v[:12])
                if st.button('恢复历史到草稿'):
                    try:
                        draft, _ = store.load(identifier, revision=revision)
                        head, _ = store.load(identifier)
                        adopt(draft, identifier, st.session_state['module-version'], store.digest(head))
                    except (ValueError, OSError) as error:
                        st.error(str(error))
            if st.button('将已保存版本移入回收区'):
                try:
                    store.trash(identifier, st.session_state['module-version'])
                    st.session_state['module-id'] = None
                    st.session_state['module-version'] = None
                    st.rerun()
                except (ValueError, OSError) as error:
                    st.error(str(error))
        deleted = dict(store.saved(deleted=True))
        if deleted:
            choice = st.selectbox('回收区方案', list(deleted), format_func=lambda i: deleted[i]+' · '+i[:8])
            if st.button('恢复为副本'):
                try:
                    draft, _ = store.load(choice, deleted=True)
                    store.save(draft)
                    st.success('已恢复到方案库，当前草稿保持。')
                except (ValueError, OSError) as error:
                    st.error(str(error))
