"""Portable generic open-loop analyses using the common trim load model."""
from time import perf_counter
import numpy as np
from .aircraft import read_aircraft,require_analysis
from .cases import run_case,read_case,write_json,write_csv,numeric
from .trim import TrimSystem
from .model_scope import OPEN_LOOP_LABEL, RESPONSE_DURATION_BOUNDS, MACH_SCOPE
from .perturbation import from_case as perturbation_from_case
from .dynamics import (ReducedDynamics,STATES,UNITS,CONTROLS,central_derivatives,
                       derivative_check,modes,frequency_response,step_response,STATE_STEPS,CONTROL_STEPS,STATE_SCALE,ResponseDomainError)

OPTIONS = {'frequencies_rad_s', 'control', 'amplitude_deg', 'duration_s', 'time_step_s',
           'input_type', 'input_start_s', 'input_duration_s'}
WARNINGS=[OPEN_LOOP_LABEL, MACH_SCOPE, '低频降阶模型：6自由度机体、动态PP入流、准定常一阶挥舞；转速固定。',
          '暂未计动态挥舞、旋翼角动量反作用、桨毂加速度耦合、尾迹曲率和发动机/传动动态。',
          '模态和响应为模型估算；未据此自动评定飞行品质等级。']


def run_open_loop(case,base,output):
    started = perf_counter()
    analysis = case['analysis']
    if analysis == 'linearize' and set(case) & (OPTIONS - {'frequencies_rad_s'}):
        raise ValueError('linearize仅接受frequencies_rad_s附加设置。')
    if not isinstance(case.get('aircraft_json'), str):
        raise ValueError('开环分析需要aircraft_json路径。')
    if analysis == 'response':
        if case.get('control') not in CONTROLS:
            raise ValueError('control必须是' + ', '.join(CONTROLS))
        amplitude = numeric(case, 'amplitude_deg', -2, 2)
        duration = numeric(case, 'duration_s', *RESPONSE_DURATION_BOUNDS)
        step = numeric(case, 'time_step_s', .0005, .05)
        if abs(duration / step - round(duration / step)) > 1e-8:
            raise ValueError('时长必须为步长整数倍。')
        perturbation = perturbation_from_case(case)
    # Trim rejects all remaining unknown fields and validates operating conditions.
    trim_case = {k: v for k, v in case.items() if k not in OPTIONS}
    trim_case['analysis'] = 'trim'
    aircraft = read_aircraft((base / case['aircraft_json']).resolve())
    require_analysis(aircraft, analysis)
    trim=run_case(trim_case,base,output/'trim')
    snapshot=dict(case,aircraft_json='trim/aircraft.json')
    if analysis == 'response':
        snapshot.update(input_type=perturbation.kind, input_start_s=perturbation.start_s)
        if perturbation.kind != 'step':
            snapshot['input_duration_s'] = perturbation.duration_s
    write_json(output/'case.json',snapshot)
    if trim['status']!='converged':
        return dict(status='failed',analysis=analysis,solver_status='trim_failed',support_status=trim['support_status'],
            design_limits_status=trim['design_limits_status'],evidence_status='model_estimate',error='开环基点未通过配平：'+trim['error'],
            trim=trim,download_model=trim.get('download_model'),warnings=WARNINGS),snapshot
    saved = read_case(output / 'trim/case.json')
    aircraft = read_aircraft(output / 'trim/aircraft.json')
    system=TrimSystem(aircraft,output/'trim',saved)
    plant=ReducedDynamics(system,trim['diagnostics']['solved_state'],trim['velocity_body_m_s'])
    equilibrium=plant.rhs(plant.state,plant.controls)
    if np.max(abs(equilibrium)) > 1e-6:
        raise ValueError('配平点代入动态方程未保持平衡。')
    a, b = central_derivatives(plant)
    fine_a, fine_b = central_derivatives(plant, .5)
    check = derivative_check(a, b, fine_a, fine_b)
    a, b = fine_a, fine_b
    maximum_frequency=min(3.,.1*system.rotors['main'].rotor.omega)
    raw_frequencies=case.get('frequencies_rad_s',np.geomspace(.1,maximum_frequency,36).tolist())
    if not isinstance(raw_frequencies, list) or any(type(v) not in (int, float) for v in raw_frequencies):
        raise ValueError('frequencies_rad_s须为数值列表。')
    frequencies=np.asarray(raw_frequencies,dtype=float)
    if frequencies.ndim!=1 or not 2<=len(frequencies)<=500 or not np.isfinite(frequencies).all() or np.any(np.diff(frequencies)<=0) or frequencies[0]<.01 or frequencies[-1]>maximum_frequency:
        raise ValueError(f'频率需要2–500个严格递增有限数，范围0.01–{maximum_frequency:g} rad/s。')
    modal=modes(a)
    unavailable = sum(mode['participation_status'] == 'unavailable' for mode in modal)
    modal_warnings = [f'{unavailable}个模态的参与因子不可用，特征根及数值诊断已保留。'] if unavailable else []
    for mode in modal:
        mode['within_low_frequency_band'] = bool(np.hypot(mode['real'], mode['imag']) <= maximum_frequency)
    metadata=dict(state_names=STATES,state_units=UNITS,control_names=CONTROLS,control_units=['rad']*4,
        state_equilibrium=plant.state.tolist(),control_equilibrium_rad=plant.controls.tolist(),
        equilibrium_derivative=equilibrium.tolist(),derivative_check=check,
        state_difference_steps=(STATE_STEPS*.5).tolist(),control_difference_steps=(CONTROL_STEPS*.5).tolist(),
        mass_matrix_definition='E*delta_x_dot = F*delta_x + G*delta_u; E=diag(m*I3,I_cg,I3,Mpp/Omega_main,Mpp/Omega_tail), Mpp=diag(128/(75pi),16/(45pi),16/(45pi)). F=E*A, G=E*B. No hidden acceleration coupling in this reduced model.',
        modes=modal,model_scope=WARNINGS,maximum_frequency_rad_s=maximum_frequency,
        download_model=trim['download_model'])
    from .mounting import coordinate_metadata
    metadata['rotor_coordinates'] = {role: coordinate_metadata(rotor) for role, rotor in system.selected.items()}
    write_json(output/'linearization.json',metadata)
    for name,matrix,columns in [('A',a,STATES),('B',b,CONTROLS),('E',plant.mass_matrix,STATES),
                                 ('F',plant.mass_matrix@a,STATES),('G',plant.mass_matrix@b,CONTROLS)]:
        write_csv(output/f'{name}.csv',['state',*columns],([label,*row] for label,row in zip(STATES,matrix)))
    write_csv(output/'modes.csv',['real_per_s','imag_rad_s','damping_ratio','period_s','e_folding_time_s','behavior','dominant_states',
              'participation_status','participation_note','eigenvector_condition','eigenpair_relative_residual'],
        ([m['real'],m['imag'],m['damping_ratio'],m['period_s'],m['e_folding_time_s'],m['behavior'],
          '; '.join(f'{k}:{v:.4f}' for k,v in m['participation'].items()),m['participation_status'],m['participation_note'],
          m['eigenvector_condition'],m['eigenpair_relative_residual']] for m in modal))
    rows=frequency_response(a,b,frequencies)
    write_csv(output/'frequency.csv',['omega_rad_s','output','input','gain','gain_db','phase_deg','real','imag'],rows)
    result=dict(status='converged' if check['passed'] else 'failed',analysis=analysis,
        solver_status='converged' if check['passed'] else 'derivative_step_sensitive',
        support_status='within_implemented_reduced_domain',design_limits_status=trim['design_limits_status'],
        feasible=trim['feasible'],violations=trim['violations'],evidence_status='model_estimate',
        model_maturity=OPEN_LOOP_LABEL,download_model=trim['download_model'],
        warnings=WARNINGS + modal_warnings + [trim['download_model']['note'], trim['download_model']['comparison_note']],
        design_limit_scope='trim base point; response checks control/attitude/data limits, transient power limits not evaluated',
        summary=dict(states=15,controls=4,unstable_modes=sum(m['real']>1e-7 for m in modal),
                     neutral_modes=sum(m['behavior']=='kinematic_neutral' for m in modal),
                     max_equilibrium_derivative=float(abs(equilibrium).max()),
                     derivative_check_pass=check['passed']),trim=trim,linearization=metadata)
    if not check['passed']:
        result['error'] = '主要导数对差分步长敏感（>2%），保留诊断与矩阵。'
    if analysis == 'response' and check['passed']:
        if step * max(abs(np.linalg.eigvals(a))) > 1:
            raise ValueError('当前步长对最快模型模态过大；请减半步长。')
        result['perturbation'] = dict(perturbation.metadata(), control=case['control'], observation_window_s=duration)
        try:
            history = step_response(plant, a, b, CONTROLS.index(case['control']), amplitude,
                                    duration, step, perturbation=perturbation)
        except ResponseDomainError as error:
            history=error.history
            write_csv(output/'partial-response.csv',['time_s',*[k+'_nonlinear' for k in STATES],*[k+'_linear' for k in STATES]],history)
            write_input_history(output, history, perturbation, plant.controls, case['control'])
            result.update(status='failed',solver_status='response_stopped',support_status='outside_implemented_reduced_domain',error=str(error),elapsed_s=perf_counter()-started)
            result['summary']['last_valid_time_s'] = float(history[-1, 0]) if len(history) else None
            report = ['# ' + OPEN_LOOP_LABEL + '：响应中止', '', str(error),
                      '求解：响应中止；数据域：超出低频模型范围；设计限制：基点见trim/，瞬态动力限制未检查；验证依据：模型估算。',
                      '已保留矩阵、实际输入input.csv和最后有效时程partial-response.csv。',
                      input_description(result['perturbation']), *result['warnings']]
            (output / 'report.md').write_text('\n\n'.join(report) + '\n', encoding='utf-8')
            from .open_loop_plots import save_figures
            save_figures(output, result)
            return result,snapshot
        write_csv(output/'response.csv',['time_s',*[k+'_nonlinear' for k in STATES],*[k+'_linear' for k in STATES]],history)
        write_input_history(output, history, perturbation, plant.controls, case['control'])
        result['summary']['duration_s']=duration
        error=history[:,1:16]-history[:,16:31]
        result['summary']['response_error_scaled_norm']=float(np.max(np.linalg.norm(error/STATE_SCALE,axis=1)))
        result['response_max_abs_error']={name:float(value) for name,value in zip(STATES,abs(error).max(axis=0))}
        result['response_error_state_scales']=STATE_SCALE.tolist()
        result['response_definition'] = 'Deltas from accepted trim; both models share perturbation. See input.csv for right-continuous actual controls; discontinuities split integration steps. Body states retain SI/rad; no position states.'
    from .open_loop_plots import save_figures
    save_figures(output,result)
    result['elapsed_s']=perf_counter()-started
    report=['# '+OPEN_LOOP_LABEL,'',f"求解：{result['solver_status']}；数据域：{result['support_status']}；设计限制：{result['design_limits_status']}；验证依据：模型估算。",'',*result['warnings'],'',
        '状态/操纵单位、基点、差分检查和参与因子见linearization.json。A/B为显式导数，E/F/G同时导出。',
        '控制量是桨叶总距与cos/sin周期变距弧度；不等同于原UH-60英寸杆量。',
        f"主要导数步长减半检查：{check['passed']}；线性不稳定根数：{result['summary']['unstable_modes']}（复共轭分别计数）。",'',
        '完整配平与参数来源见trim/；将本目录搬移后运行case.json可复算。']
    if 'perturbation' in result:
        report += ['', input_description(result['perturbation']), '实际输入见input.csv和input.png；阶跃/双脉冲的CSV断点值按右侧定义。']
    (output/'report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    return result,snapshot


def write_input_history(output, history, perturbation, controls, selected):
    """Write actual input at every accepted output time, including split knots."""
    rows = []
    index = CONTROLS.index(selected)
    for row in history:
        delta_deg = perturbation.value_deg(row[0])
        actual = np.asarray(controls).copy()
        actual[index] += np.deg2rad(delta_deg)
        rows.append([row[0], delta_deg, *actual])
    write_csv(output / 'input.csv', ['time_s', 'control_delta_deg', *[name + '_rad' for name in CONTROLS]], rows)


def input_description(info):
    from .presentation import CONTROL_LABELS
    duration = f"每段持续{info['duration_s']:g} s" if info['duration_s'] is not None else '开始后持续保持'
    return (f"扰动：{CONTROL_LABELS[info['control']]}，{info['definition']}；峰值{info['amplitude_deg']:g}°，"
            f"开始{info['start_s']:g} s，{duration}；观察窗口{info['observation_window_s']:g} s。")
