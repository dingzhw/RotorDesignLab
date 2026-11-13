"""Adjacent-point continuation with portable, separately classified trim results."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import os
from tempfile import gettempdir

from . import __version__
from .aircraft import read_aircraft,snapshot_aircraft
from .cases import read_case,write_json,write_csv,run_case
from .hover import VARIABLES
from .hover_batch import design_points

AXES=VARIABLES|{'speed_m_s','climb_m_s','cg_x_m'}


def plot_trim(rows,axes,output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(gettempdir())/'rotordesignlab-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    first,*others=axes;second=others[0] if others else None
    panelspec=[('required_power_w',.001,'Required shaft power / kW'),
               ('duration_margin_w',.001,'Power margin / kW'),('main_collective_deg',1,'Main collective / deg'),
               ('tail_collective_deg',1,'Tail collective / deg'),('pitch_deg',1,'Body pitch / deg'),('roll_deg',1,'Body roll / deg')]
    for name,spec in [('performance',panelspec),('controls',[(k,1,k+' / deg') for k in ('main_cos_deg','main_sin_deg')])]:
        fig,panels=plt.subplots(len(spec)//2,2,figsize=(12,3.6*(len(spec)//2)),layout='constrained',squeeze=False)
        for group in axes[second] if second else [None]:
            points=sorted((r for r in rows if second is None or r[second]==group),key=lambda r:r[first])
            x=np.array([r[first] for r in points]);label=f'{second}={group:g}' if second else 'Trim'
            for panel,(key,factor,title) in zip(panels.flat,spec):
                y=np.array([r.get(key,float('nan'))*factor for r in points])
                panel.plot(x,y,'o-',label=label,markersize=3)
                bad=[i for i,r in enumerate(points) if r['status']=='converged' and not r['feasible']]
                panel.scatter(x[bad],y[bad],marker='x',color='crimson',zorder=4)
                panel.set(xlabel=first+' (SI)',ylabel=title);panel.grid(alpha=.25)
        panels[0,0].legend(fontsize=8)
        fig.suptitle('Steady six-component trim | gaps = failed/domain rejected | red x = supplied limit exceeded')
        for ext in ('png','svg'):fig.savefig(output/f'{name}.{ext}',dpi=140)
        plt.close(fig)


def run_trim_batch(spec,base,output):
    started=perf_counter();output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('输出目录已有文件，请指定新的空目录。')
    with (output/'run.lock').open('x'):pass
    result=dict(schema_version=1,solver_version=__version__,model='helicopter_trim_batch',status='failed',summary={},
                evidence_status='model_estimate',warnings=[])
    saved=deepcopy(spec)
    try:
        if set(spec)-{'schema_version','kind','case_json','axes','continuation'}:raise ValueError('配平扫描含未识别字段。')
        if type(spec.get('continuation',True)) is not bool:raise ValueError('continuation必须为布尔值。')
        check={k:v for k,v in spec.items() if k!='continuation'};check['kind']='helicopter_sweep'
        design_points(check,AXES)  # Reuse limits, finite/duplicate checks; order is set below.
        if not isinstance(spec['case_json'],str):raise ValueError('case_json必须为路径。')
        source=(base/spec['case_json']).resolve();case=read_case(source)
        if not isinstance(case,dict) or case.get('model')!='helicopter' or case.get('analysis')!='trim':raise ValueError('配平扫描需要helicopter/trim工况。')
        if not isinstance(case.get('aircraft_json'),str):raise ValueError('工况需要aircraft_json。')
        path=(source.parent/case['aircraft_json']).resolve();snapshot_aircraft(read_aircraft(path),path.parent,output)
        case['aircraft_json']='aircraft.json';write_json(output/'input-case.json',case)
        saved['case_json']='input-case.json';axes=spec['axes'];first,*rest=axes;second=rest[0] if rest else None
        rows=[]
        # Each second-axis value starts a fresh continuation chain; first axis ascends.
        for group in axes[second] if second else [None]:
            seed=None;previous=None
            for value in sorted(axes[first]):
                changes={first:value,**({second:group} if second else {})}
                current=dict(case,**changes)
                if seed is not None and spec.get('continuation',True):current['initial_state']=seed
                name=f'point-{len(rows):04d}';answer=run_case(current,output,output/name)
                row=dict(case_id=name,**changes,status=answer['status'],feasible=answer.get('feasible',False),
                    solver_status=answer.get('solver_status','failed'),
                    support_status=answer.get('support_status','not_established'),design_limits_status=answer.get('design_limits_status','not_evaluated'),
                    evidence_status='model_estimate',failure_kind=answer.get('failure_kind',''),error=answer.get('error',''),
                    continuation_from=previous if seed is not None and spec.get('continuation',True) else '')
                row.update(answer.get('summary',{}));row['elapsed_s']=answer.get('elapsed_s',answer.get('diagnostics',{}).get('elapsed_s',''))
                rows.append(row)
                if answer['status']=='converged':seed=answer['diagnostics']['solved_state'];previous=name
        headers=list(dict.fromkeys(k for row in rows for k in row))
        write_csv(output/'performance.csv',headers,([r.get(k,'') for k in headers] for r in rows))
        failed=sum(r['status']!='converged' for r in rows)
        result['summary']=dict(total=len(rows),converged=len(rows)-failed,failed=failed,
            limit_violations=sum(r['status']=='converged' and not r['feasible'] for r in rows))
        result['status']='converged' if not failed else ('partial' if failed<len(rows) else 'failed')
        if failed:result['error']=f'{failed}个点未获得有效配平，详见各点诊断。'
        plot_trim(rows,axes,output)
        lines=['# 整机配平扫描','', '第一轴升序续接；第二轴各组独立起算。失败点保留诊断；收敛点仍分别检查数据域、操纵和功率限制。','',
            '|工况|总体状态|方程状态|数据域|设计限制|功率 kW|俯仰 °|滚转 °|失败类别|','|---|---|---|---|---|---:|---:|---:|---|']
        for r in rows:
            numbers=[f'{r[k]*factor:.5g}' if k in r else '—' for k,factor in [('required_power_w',.001),('pitch_deg',1),('roll_deg',1)]]
            lines.append('|'+ '|'.join([r['case_id'],r['status'],r['solver_status'],r['support_status'],r['design_limits_status'],*numbers,r['failure_kind']])+'|')
        lines+=['','所有结果为模型估算。各点case.json包含实际初值和完整机型，可独立搬移复算。',
                'performance.csv保存全部操纵与动力指标；performance/controls.png和.svg用于比较。验证范围见docs/trim.md。']
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    except (ValueError,OSError,RuntimeError) as error:result['error']=str(error)
    finally:
        result['elapsed_s']=perf_counter()-started
        try:write_json(output/'batch.json',saved)
        except (ValueError,TypeError):result.update(status='failed',error='批量输入含不可保存数值。')
        write_json(output/'result.json',result);(output/'run.lock').unlink()
    return result
