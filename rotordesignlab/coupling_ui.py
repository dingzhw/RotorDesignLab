"""Explicit model switch and reference-mass declaration for modular aircraft."""
from copy import deepcopy
import pandas as pd
import streamlit as st
from . import assembly
from .design_ui import current
from .mass_partition import MODEL, LEGACY, Partition


def render():
    design = current()
    epoch = st.session_state['design_epoch']
    cfg = design['aircraft'].get('dynamics', {})
    with st.expander('动力学模型与质量归属'):
        st.caption('旋翼本体质量在孤立旋翼中填写并显式换入装配；这里声明总质量、重心、惯量包含哪些部件，以及测量或估算时的桨叶姿态。')
        with st.form('coupling:'+str(epoch)):
            model = st.selectbox('整机载荷与动力学模型', [LEGACY, MODEL], index=int(bool(cfg)),
                format_func=lambda value: '历史气动载荷模型（原方案语义）' if value == LEGACY else '质量分账＋动态一阶挥舞（试验性）',
                help='新模型联立桨叶、旋转桨毂和机体加速度。旧包不会自动切换，开环仍受R19验收限制。')
            st.caption('以下参考构型仅在新模型使用；总质量和惯量须包含主尾桨全部桨叶及旋转桨毂。')
            reference = {}
            for rotor in design['aircraft']['rotors']:
                values = cfg.get('reference_flap_deg', {}).get(rotor['id'], [rotor['flight']['flapping']['precone_deg'],0.,0.])
                title = '主旋翼' if rotor['role'] == 'main' else '尾桨'
                reference[rotor['id']] = [col.number_input(title+'参考'+label+' / °', value=float(value),
                    help='总质量性质对应的方位平均桨叶构型。不是配平求得的挥舞；未知应先核对资料。')
                    for col,label,value in zip(st.columns(3), ['锥度','cos挥舞','sin挥舞'], values)]
            note = st.text_area('总质量与参考惯量来源说明', value=cfg.get('provenance',''),
                                help='注明全机是否含主尾桨桨叶/旋转桨毂，参考构型、测量或估算依据；不要直接把不明归属的旧惯量作为已知。')
            acknowledged = st.checkbox('已确认全机值包含全部旋转部件，且参考构型与来源明确', value=bool(cfg))
            if st.form_submit_button('应用动力学模型与质量归属'):
                if model == MODEL and (not acknowledged or not note.strip()):
                    st.error('请填写来源并确认质量归属，原方案保持。')
                else:
                    candidate = deepcopy(design)
                    if model == MODEL:
                        candidate['aircraft']['dynamics'] = dict(model=MODEL, mass_reference='total_at_reference_flap',
                                                               reference_flap_deg=reference, provenance=note)
                    else:
                        candidate['aircraft'].pop('dynamics',None)
                    assembly.refresh(candidate)
                    from .assembly_ui import update_design
                    update_design(candidate)
                    st.rerun()
        if cfg:
            try:
                report = Partition(design['aircraft']).report
                rows = [{'部件':'非旋转机体', '质量 / kg':report['core_mass_kg']}]
                for item in report['components']:
                    rows.extend([{'部件':item['rotor_id']+'全部桨叶','质量 / kg':item['blades_mass_kg']},
                                 {'部件':item['rotor_id']+'旋转桨毂','质量 / kg':item['hub_mass_kg']}])
                st.dataframe(pd.DataFrame(rows),hide_index=True)
                st.caption('扣除后的机体重心 / m：'+str(report['core_cg_m']))
                st.caption('惯量已检查正定性和主惯量三角关系；输入来源和独立物理精度仍须分别核实。')
            except (ValueError,KeyError,TypeError) as error:
                st.error('新模型质量分账暂不完整：'+str(error))
