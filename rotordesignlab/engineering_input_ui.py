"""Preview before applying; callbacks own atomic module/design replacement."""
import streamlit as st
import csv
import numpy as np
import pandas as pd
from .engineering_inputs import generate_geometry, export_table, import_table
from .parameter_fields import label


def geometry_generator(frame, reference, key, apply, optional_source=False):
    with st.expander('生成直线变弦与线性扭转桨叶'):
        st.caption('根部指有效气动桨根。扭转增加表示桨距增加；求解时扣除总距参考站扭转。生成几何不改变半径、质量矩、桨毂或挥舞参数。')
        try:
            complete = len(frame)>=2 and frame.shape[1]==3 and np.isfinite(frame.to_numpy(dtype=float)).all()
        except (ValueError, TypeError):
            complete = False
        if not complete:
            st.caption('当前几何表不完整，以下提供可编辑的生成初值；点击应用前原表保持。')
            frame = pd.DataFrame([[.2,.1,0.],[1.,.1,0.]], columns=['r_over_R','chord_m','twist_deg'])
        specs = [('root', '有效桨根 r/R', frame.iloc[0, 0]),
                 ('root-chord', '有效桨根弦长 / m', frame.iloc[0, 1]),
                 ('tip-chord', '桨尖弦长 / m', frame.iloc[-1, 1]),
                 ('root-twist', '有效桨根扭转 / °', frame.iloc[0, 2]),
                 ('tip-twist', '桨尖扭转 / °', frame.iloc[-1, 2])]
        values = [st.number_input(title, value=float(default), key=key(name),
                                  help='按方案输入，单位见名称；有效桨根至桨尖之间采用线性分布。')
                  for name, title, default in specs]
        count = st.number_input('生成几何站数', value=min(1000, max(2, len(frame))), min_value=2, max_value=1000, key=key('stations'),
                                help='几何描述站数，不是求解叶素数；线性几何无需用很多站点。')
        if optional_source:
            with st.expander('生成备注（可选）'):
                source = st.text_input('生成几何的来源说明', value='', key=key('source'))
            source = source.strip() or '用户参数化生成（工程估计）；结构质量及惯量未重估。'
        else:
            source = st.text_input('生成几何的来源说明', value='总体设计参数化估算；结构质量及惯量未重估。', key=key('source'))
        try:
            generated = generate_geometry(*values, count, reference)
            st.dataframe(generated.rename(columns={'r_over_R':'半径比 r/R', 'chord_m':'实际弦长 / m', 'twist_deg':'几何扭转 / °'}), hide_index=True)
            if st.button('应用生成几何', key=key('apply')):
                if not source.strip():
                    raise ValueError('请填写生成几何的来源说明。')
                apply(generated, source)
        except ValueError as error:
            st.error(str(error))


def table_exchange(frame, title, source, key, apply, optional_source=False):
    st.download_button('下载'+title+'中文 CSV', export_table(frame, source), title+'.csv', key=key('download'))
    upload = st.file_uploader('导入'+title+' CSV/TXT', type=['csv','txt'], key=key('upload'),
                              help='可用Excel打开下载的CSV；支持中文或原英文字段，UTF-8/GB18030，逗号或制表符。来源说明随表保存。')
    if upload is not None:
        try:
            incoming = import_table(upload.getvalue(), list(frame.columns))
            st.caption('导入预览（点击应用后才替换当前表）')
            st.dataframe(incoming.rename(columns={column:label(column) for column in incoming.columns}), hide_index=True)
            if optional_source:
                with st.expander('导入备注（可选）'):
                    note = st.text_input(title+'导入来源说明', value=incoming.attrs['source'], key=key('source'),
                                         help='自动读取表内来源；缺项可留空，按用户导入待核记录。')
                note = note.strip() or '用户导入（来源待核）'
            else:
                note = st.text_input(title+'导入来源说明', value=incoming.attrs['source'], key=key('source'),
                                     help='填写资料名称、工况及测量/数字化/工程估计性质。旧来源会保留。')
            if st.button('应用'+title+'导入', key=key('apply')):
                if not note.strip():
                    raise ValueError('请补充数据来源说明。')
                apply(incoming, note)
        except (ValueError, UnicodeError, csv.Error) as error:
            st.error('导入失败，原表保留：'+str(error))
