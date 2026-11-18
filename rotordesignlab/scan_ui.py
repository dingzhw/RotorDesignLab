"""Range inputs expand to the original explicit lists before solver entry."""
import streamlit as st
from decimal import Decimal
from .engineering_inputs import scan_range


def design_scan(setting, task, name, title, default, help):
    mode = setting(task, name+'-mode', title+'输入方式', '数值点列', ['数值点列', '起点/终点/步长'],
                   help='旧点列原样保留。步长方式不补入偏离步长的终点；结果保存实际点列。')
    if mode == '数值点列':
        return setting(task, name, title, default, help=help)
    original = [float(value) for value in default.split(',')]
    start = setting(task, name+'-start', title+'起点', original[0], help=help)
    stop = setting(task, name+'-stop', title+'终点', original[-1], help=help)
    initial_step = float(Decimal(str(original[1]))-Decimal(str(original[0]))) if len(original)>1 else 1.
    step = setting(task, name+'-step', title+'步长', initial_step, help='步长与起止方向一致，不能为零；单位与扫描参数一致。')
    points = scan_range(start, stop, step)
    st.caption(f'实际{len(points)}点：'+', '.join(f'{value:g}' for value in points))
    return ','.join(repr(value) for value in points)
