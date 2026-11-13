"""Portable hover design sweeps and named candidate comparisons."""
from copy import deepcopy
from itertools import product
from math import isfinite
import os
from pathlib import Path
from tempfile import gettempdir
from time import perf_counter

from . import __version__
from .aircraft import read_aircraft, snapshot_aircraft
from .cases import read_case, run_case, write_csv, write_json
from .hover import VARIABLES


def finite_values(values):
    return (isinstance(values,list) and bool(values) and
            all(type(v) in (int,float) and isfinite(v) for v in values))


def design_points(spec):
    kind = spec.get('kind')
    expected = {'schema_version','kind','case_json', 'axes' if kind=='helicopter_sweep' else 'variants'}
    if set(spec) != expected or type(spec.get('schema_version')) is not int or spec['schema_version']!=1:
        raise ValueError('整机批量需要版本1、kind、case_json及 axes 或 variants，且不接受其它字段。')
    if kind == 'helicopter_sweep':
        axes=spec['axes']
        if not isinstance(axes,dict) or not 1<=len(axes)<=2 or set(axes)-VARIABLES:
            raise ValueError('整机扫描需要1–2个支持的设计变量。')
        for key,values in axes.items():
            if not finite_values(values) or len(set(values))!=len(values):
                raise ValueError(f'{key} 扫描必须为有限数值列表且不得重复。')
        if len(axes)==2 and len(list(axes.values())[1])>12:
            raise ValueError('分组曲线最多12条。')
        if __import__('math').prod(len(v) for v in axes.values())>1000:
            raise ValueError('最多1000个设计点。')
        return [(f'point-{i:04d}',dict(zip(axes,values))) for i,values in enumerate(product(*axes.values()))]
    variants=spec['variants']
    if not isinstance(variants,list) or not 1<=len(variants)<=12:
        raise ValueError('比较需要1–12组方案。')
    points=[]
    for item in variants:
        if not isinstance(item,dict) or set(item)!={'name','overrides'} or not isinstance(item['name'],str) or not item['name'].strip():
            raise ValueError('方案需要非空 name 和 overrides。')
        changes=item['overrides']
        if not isinstance(changes,dict) or set(changes)-VARIABLES or (changes and not finite_values(list(changes.values()))):
            raise ValueError('方案 overrides 含不支持的变量或数值。')
        points.append((item['name'],changes))
    if len({name for name,_ in points})!=len(points):raise ValueError('方案名称不得重复。')
    return points


def plot(rows, axes, output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(gettempdir())/'rotordesignlab-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,panels=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    first=next(iter(axes),None)
    second=list(axes)[1] if len(axes)==2 else None
    groups=axes[second] if second else [None]
    for group in groups:
        points=[row for row in rows if second is None or row[second]==group]
        if first:points=sorted(points,key=lambda r:r[first])
        x=[row[first] for row in points] if first else list(range(1,len(points)+1))
        label=f'{second}={group:g}' if second else 'Budget'
        for panel,(key,factor,title) in zip(panels.flat,[
                ('required_power_w',.001,'Required shaft power / kW'),
                ('duration_margin_w',.001,'Power margin for requested duration / kW'),
                ('tail_thrust_n',1,'Tail thrust / N'),('main_collective_deg',1,'Main collective at reference / deg')]):
            y=[row.get(key,float('nan'))*factor for row in points]
            panel.plot(x,y,'o-',label=label,markersize=4)
            bad=[i for i,row in enumerate(points) if row['status']=='converged' and not row['feasible']]
            panel.scatter(np.asarray(x)[bad],np.asarray(y)[bad],marker='x',color='crimson',zorder=4)
            panel.set(xlabel=first or 'Candidate index (names in CSV/report)',ylabel=title)
            panel.grid(alpha=.25)
            if not first:panel.set_xticks(x)
    panels[0,0].legend(fontsize=8);panels[0,1].axhline(0,color='black',linewidth=.7)
    fig.suptitle('Hover power/load budget (not six-axis trim); red x = supplied limit exceeded')
    for ext in ('png','svg'):fig.savefig(output/f'performance.{ext}',dpi=140)
    plt.close(fig)


def run_hover_batch(spec, base, output):
    started=perf_counter();output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('输出目录已有文件，请指定新的空目录。')
    with (output/'run.lock').open('x'):pass
    saved=deepcopy(spec)
    result=dict(schema_version=1,solver_version=__version__,model='helicopter_batch',status='failed',summary={},
                warnings=['无地效悬停功率与载荷预算；尚未进行整机六分量配平。'],evidence_status='model_estimate')
    try:
        points=design_points(spec)
        if not isinstance(spec['case_json'],str):raise ValueError('case_json 必须为路径。')
        case_path=(base/spec['case_json']).resolve();case=read_case(case_path)
        if not isinstance(case,dict) or case.get('model')!='helicopter' or case.get('analysis')!='hover_budget':
            raise ValueError('批量仅接受 helicopter/hover_budget 工况。')
        if not isinstance(case.get('aircraft_json'),str):raise ValueError('工况需要 aircraft_json。')
        path=(case_path.parent/case['aircraft_json']).resolve()
        snapshot_aircraft(read_aircraft(path),path.parent,output)
        case['aircraft_json']='aircraft.json';write_json(output/'input-case.json',case)
        saved['case_json']='input-case.json'
        rows=[]
        for i,(name,changes) in enumerate(points):
            answer=run_case(dict(case,**changes),output,output/f'point-{i:04d}')
            row=dict(case_id=f'point-{i:04d}',name=name,**changes,status=answer['status'],
                     feasible=answer.get('feasible',False),support_status=answer.get('support_status'),
                     design_limits_status=answer.get('design_limits_status'),evidence_status='model_estimate',
                     error=answer.get('error',''))
            row.update(answer.get('summary',{}))
            rows.append(row)
        headers=list(dict.fromkeys(key for row in rows for key in row))
        write_csv(output/'performance.csv',headers,([row.get(key,'') for key in headers] for row in rows))
        failed=sum(r['status']!='converged' for r in rows)
        result['summary']=dict(total=len(rows),converged=len(rows)-failed,failed=failed,
            limit_violations=sum(r['status']=='converged' and not r['feasible'] for r in rows))
        result['status']='converged' if not failed else ('partial' if failed<len(rows) else 'failed')
        if failed:result['error']=f'{failed} 个工况未求得有效预算；逐点诊断已保留。'
        plot(rows,spec.get('axes',{}),output)
        lines=['# 悬停方案比较', '', '数据为各方案实际运行输入；半径变化保持弦长/扭转及 r/R 站位。',
               'Fz/Mz 闭合，其它力和力矩见各点结果；所有点均为模型估算。', '',
               '|编号/方案|求解|限制|主桨 kW|尾桨 kW|传动损失 kW|附件 kW|总需求 kW|时长余量 kW|尾桨 N|',
               '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for i,row in enumerate(rows):
            name=row['name'].replace('|','/').replace('\n',' ')
            values=[f"{row[k]*.001:.3f}" if k in row else '—' for k in
                    ('main_power_w','tail_power_w','transmission_loss_w','accessory_power_w','required_power_w','duration_margin_w')]
            values.append(f"{row['tail_thrust_n']:.3f}" if 'tail_thrust_n' in row else '—')
            lines.append('|'+ '|'.join([f'{i+1}: {name}',row['status'],row.get('design_limits_status',''),*values])+'|')
        lines+=['','CSV 保存所有参数、盘载、桨尖速度、T/Q/P、总距、限制与失败原因。',
                '各 point 目录含实际机型、几何、翼型、工况和哈希；batch.json 支持整体搬移复算。']
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    except (OSError,ValueError,RuntimeError) as error:result['error']=str(error)
    finally:
        result['elapsed_s']=perf_counter()-started
        try:
            write_json(output/'batch.json',saved)
        except (ValueError,TypeError):result.update(status='failed',error='批量输入含不可保存的数值。')
        write_json(output/'result.json',result);(output/'run.lock').unlink()
    return result
