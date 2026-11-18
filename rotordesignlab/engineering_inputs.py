"""User-facing numeric tables and explicit geometry/range generation in SI."""
import csv
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from io import StringIO
import math

import numpy as np
import pandas as pd
from .parameter_fields import label

GEOMETRY = ['r_over_R', 'chord_m', 'twist_deg']
POLAR = ['alpha_deg', 'cl', 'cd']


def scan_range(start, stop, step, maximum=1000):
    """Inclusive bound, fixed signed step; never append an off-grid endpoint."""
    try:
        a, b, h = [Decimal(str(v)) for v in (start, stop, step)]
        if not all(v.is_finite() for v in (a, b, h)) or h == 0:
            raise ValueError('起点、终点和步长必须有限，步长不能为零。')
        if (b-a)*h < 0:
            raise ValueError('步长方向与起点到终点的方向相反。')
        count = int(((b-a)/h).to_integral_value(rounding=ROUND_FLOOR))+1
        if not 1 <= count <= maximum:
            raise ValueError(f'此扫描轴需要{count}点，允许1–{maximum}点。')
        result = [float(a+i*h) for i in range(count)]
        if not all(math.isfinite(v) for v in result) or len(set(result)) != count:
            raise ValueError('步长太小或数值过大，无法生成可区分的有限扫描点。')
        return result
    except InvalidOperation as error:
        raise ValueError('起点、终点、步长须为有效数值。') from error


def generate_geometry(root, root_chord, tip_chord, root_twist, tip_twist, stations, reference):
    values = [root, root_chord, tip_chord, root_twist, tip_twist, reference]
    if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
        raise ValueError('桨叶几何参数须为有限数值。')
    if not 0 < root < 1 or not root <= reference <= 1:
        raise ValueError('有效桨根需满足0<r/R<1，且总距参考站须位于有效桨叶内。')
    if min(root_chord, tip_chord) <= 0:
        raise ValueError('根弦和梢弦必须大于零。')
    if type(stations) is not int or not 2 <= stations <= 1000:
        raise ValueError('几何站数须为2–1000的整数。')
    return pd.DataFrame(dict(r_over_R=np.linspace(root, 1., stations),
                             chord_m=np.linspace(root_chord, tip_chord, stations),
                             twist_deg=np.linspace(root_twist, tip_twist, stations)))


def export_table(frame, source=''):
    output = frame.rename(columns={key: label(key) for key in frame.columns}).copy()
    if source:
        output['来源说明'] = source
    return output.to_csv(index=False).encode('utf-8-sig')


def import_table(data, columns):
    if len(data) > 8*1024**2:
        raise ValueError('数据表超过8 MB。')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = data.decode('gb18030')
        except UnicodeDecodeError as error:
            raise ValueError('请保存为UTF-8或GB18030文本。') from error
    first = text.splitlines()[0] if text.splitlines() else ''
    separator = '\t' if '\t' in first else ','
    reader = csv.reader(StringIO(text), delimiter=separator)
    headers = next(reader, [])
    aliases = {label(key):key for key in columns}
    headers = [aliases.get(value.strip(), value.strip()) for value in headers]
    if len(set(headers)) != len(headers) or set(headers)-{'来源说明'} != set(columns):
        raise ValueError('第1行列名不符或重复；需要：'+ '、'.join(label(k) for k in columns)+'（可附来源说明）。')
    rows, sources, line_numbers = [], [], []
    for values in reader:
        line = reader.line_num
        if not values or all(not value.strip() for value in values):
            continue
        if len(values) != len(headers):
            raise ValueError(f'第{line}行列数与表头不一致。')
        item = dict(zip(headers, values))
        row = []
        for key in columns:
            try:
                value = float(item[key])
                if not math.isfinite(value):
                    raise ValueError()
            except ValueError as error:
                raise ValueError(f'第{line}行“{label(key)}”须填写有限数值。') from error
            row.append(value)
        rows.append(row)
        line_numbers.append(line)
        if item.get('来源说明', '').strip() and item['来源说明'] not in sources:
            sources.append(item['来源说明'])
        if len(rows) > 10000:
            raise ValueError('数据表最多10000行。')
    if len(rows) < 2:
        raise ValueError('数据表至少需要两行数值。')
    frame = pd.DataFrame(rows, columns=columns)
    axis = frame.iloc[:, 0].to_numpy()
    if np.any(np.diff(axis) <= 0):
        index = line_numbers[int(np.flatnonzero(np.diff(axis) <= 0)[0])+1]
        raise ValueError(f'第{index}行附近“{label(columns[0])}”须严格递增，不自动排序。')
    if list(columns) == GEOMETRY:
        if not 0 < axis[0] < 1 or axis[-1] != 1:
            raise ValueError('有效桨根半径比须大于0、末站须为1。')
        if (frame['chord_m'] <= 0).any():
            index = line_numbers[int(np.flatnonzero(frame['chord_m'].to_numpy() <= 0)[0])]
            raise ValueError(f'第{index}行实际弦长须大于零。')
    if 'cd' in frame and (frame['cd'] < 0).any():
        raise ValueError('阻力系数CD不得为负。')
    frame.attrs['source'] = '；'.join(sources)
    return frame
