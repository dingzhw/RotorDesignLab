"""Editable Chinese CSV for the three candidates; task conditions stay shared."""
from io import StringIO
import csv
import math
import pandas as pd
from .design_comparison import RULES

COLUMNS = {'name':'方案名称', 'main_radius_m':'主桨半径 / m', 'main_rpm':'主桨转速 / rpm',
           'tail_radius_m':'尾桨半径 / m', 'tail_arm_m':'尾桨纵向力臂 / m', 'cg_x_m':'重心X / m',
           'geometry_rule':'半径变化规则', 'provenance':'来源说明'}


def export_candidates(items):
    frame = pd.DataFrame(items, columns=list(COLUMNS))
    frame['geometry_rule'] = frame['geometry_rule'].map(RULES)
    return frame.rename(columns=COLUMNS).to_csv(index=False).encode('utf-8-sig')


def import_candidates(data):
    if len(data)>1024**2:
        raise ValueError('候选表超过1 MB。')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('gb18030')
    if not text.strip():
        raise ValueError('候选表为空。')
    separator = '\t' if '\t' in text.splitlines()[0] else ','
    reader = csv.DictReader(StringIO(text), delimiter=separator)
    if reader.fieldnames != list(COLUMNS.values()):
        raise ValueError('候选表列名与顺序须与下载模板一致。')
    result = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'第{reader.line_num}行列数不正确。')
        values = {key:row[title].strip() for key,title in COLUMNS.items()}
        for key in ('main_radius_m','main_rpm','tail_radius_m','tail_arm_m','cg_x_m'):
            try:
                values[key] = float(values[key])
                if not math.isfinite(values[key]):
                    raise ValueError()
            except ValueError as error:
                raise ValueError(f'第{reader.line_num}行“{COLUMNS[key]}”须为有限数值。') from error
        rules = {**{value:key for key,value in RULES.items()}, **{key:key for key in RULES}}
        if values['geometry_rule'] not in rules:
            raise ValueError(f'第{reader.line_num}行半径规则不受支持。')
        values['geometry_rule'] = rules[values['geometry_rule']]
        if not values['name'] or len(values['name'])>80 or not values['provenance']:
            raise ValueError(f'第{reader.line_num}行需填写名称（最多80字）与来源说明。')
        result.append(values)
    if len(result)!=3 or len({item['name'] for item in result})!=3:
        raise ValueError('需要恰好三行、三个不同名称的候选方案。')
    return result
