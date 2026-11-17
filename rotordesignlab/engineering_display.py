"""Chinese engineering labels and display units, with SI files unchanged."""
import pandas as pd
from .parameter_fields import FIELDS
from .presentation import AXIS_LABELS, CONTROL_LABELS, STATE_LABELS

NAMES = {
    'lambda0': '均匀入流 λ₀', 'lambdac': 'cos入流 λc', 'lambdas': 'sin入流 λs',
    'weight_n': '重量 / N', 'continuous_available_w': '连续可用轴功率 / W',
    'short_time_available_w': '短时可用轴功率 / W', 'max_scaled_balance_residual': '预算最大归一化残差',
    'within_budget_input_domain': '在预算输入范围内',
    'solved_rpm': '实际旋翼转速 / rpm', 'solved_collective_deg': '实际总距 / °',
    'target_relative_error': '目标拉力相对误差', 'power_margin_w': '旋翼功率余量 / W',
    'torque_margin_nm': '旋翼扭矩余量 / (N·m)', 'variant': '候选方案', 'name': '名称',
    'disk_loading_n_m2': '盘载 / (N/m²)', 'tip_speed_m_s': '桨尖速度 / (m/s)',
    'main_disk_loading_n_m2': '主桨盘载 / (N/m²)', 'main_tip_speed_m_s': '主桨桨尖速度 / (m/s)',
    'tail_tip_speed_m_s': '尾桨桨尖速度 / (m/s)', 'tail_side_force_n': '尾桨侧力 / N',
    'force_residual_n': '力残差 / N', 'yaw_moment_residual_nm': '偏航力矩残差 / (N·m)',
    'vertical_residual_n': '垂向力残差 / N', 'yaw_residual_nm': '偏航力矩残差 / (N·m)',
    'relative_thrust_error': '拉力相对误差', 'within_supplied_limits': '满足给定限制',
    'real_per_s': '实部 / (1/s)', 'imag_rad_s': '虚部 / (rad/s)', 'dominant_states': '主要参与状态',
    'phi': '滚转姿态 φ', 'theta': '俯仰姿态 θ', 'psi': '航向 ψ',
    'quantity': '物理量', 'value': '数值', 'unit': '单位', 'rotor_id': '旋翼', 'case_id': '工况编号',
    'status': '计算状态', 'error': '失败原因', 'feasible': '满足限制', 'solver_status': '求解状态',
    'support_status': '支持范围', 'design_limits_status': '设计限制', 'evidence_status': '验证依据',
    'thrust_n': '拉力 / N', 'torque_nm': '轴扭矩 / (N·m)', 'power_w': '轴功率 / W',
    'required_power_w': '整机需用轴功率 / W', 'continuous_margin_w': '连续功率余量 / W',
    'short_time_margin_w': '短时功率余量 / W', 'duration_margin_w': '本次功率余量 / W',
    'transmission_loss_w': '传动损失 / W', 'download_n': '附加下载 / N',
    'max_scaled_residual': '六分量最大归一化残差', 'max_internal_residual': '旋翼内部最大残差',
    'main_collective_deg': '主桨总距 / °', 'tail_collective_deg': '尾桨总距 / °',
    'roll_deg': '滚转姿态 / °', 'pitch_deg': '俯仰姿态 / °', 'index': '编号', 'real': '实部 / (1/s)',
    'imag': '虚部 / (rad/s)', 'damping_ratio': '阻尼比', 'period_s': '振荡周期 / s',
    'e_folding_time_s': '衰减或发散时间 / s', 'behavior': '模态性质', 'participation': '主要参与状态',
    'participation_status': '参与因子可靠性', 'participation_note': '参与因子说明',
    'eigenvector_condition': '特征向量条件数', 'eigenpair_relative_residual': '特征对相对残差',
    'mode': '模态编号', 'to_lower': '距下限 / °', 'to_upper': '距上限 / °',
    'converged': '收敛', 'failed': '失败', 'satisfied': '满足', 'exceeded': '超限',
    'not_evaluated': '未评估', 'not_established': '未确定', 'model_estimate': '模型估算',
    'stable': '稳定', 'unstable': '不稳定', 'near_neutral': '近中性', 'kinematic_neutral': '运动学中性',
    'available': '可用', 'unavailable': '不可用', 'ill_conditioned': '条件不良',
    'within_domain': '在数据域内', 'within_implemented_steady_domain': '在当前稳态模型范围内',
    'within_implemented_reduced_domain': '在当前低频模型范围内',
    'outside_implemented_domain': '超出当前模型范围', 'trim_failed': '配平失败',
    'derivative_step_sensitive': '导数对差分步长敏感', 'not_converged': '未收敛',
}


def label(key):
    if key in NAMES:
        return NAMES[key]
    if key in AXIS_LABELS:
        return AXIS_LABELS[key]
    if key in FIELDS:
        return FIELDS[key][0]
    if key in CONTROL_LABELS:
        return CONTROL_LABELS[key]
    if key in STATE_LABELS:
        return STATE_LABELS[key]
    for prefix, title in (('main_', '主桨'), ('tail_', '尾桨')):
        if key.startswith(prefix):
            rest = key[len(prefix):]
            if rest in NAMES or rest in AXIS_LABELS:
                return title + label(rest)
    return key


def is_power(key):
    return key.endswith('power_w') or key in ('continuous_available_w', 'short_time_available_w', 'power_margin_w', 'continuous_margin_w', 'short_time_margin_w', 'duration_margin_w', 'transmission_loss_w')


def display_label(key):
    name = label(key)
    return name.replace('/ W', '/ kW') if is_power(key) else name


def result_table(frame):
    output = frame.copy(deep=True)
    for key in output.columns:
        if is_power(key) and pd.api.types.is_numeric_dtype(output[key]):
            output[key] = output[key] / 1000.
        elif key == 'dominant_states':
            output[key] = output[key].map(dominant_states)
        elif output[key].dtype == object or pd.api.types.is_string_dtype(output[key]):
            output[key] = output[key].map(lambda value: label(value) if isinstance(value, str) else value)
    # Vertical quantity/value CSVs need row-specific conversion before renaming.
    if 'quantity' in output and 'value' in output:
        output['value'] = output['value'].astype(object)
        for index, key in enumerate(frame['quantity']):
            if isinstance(key, str):
                output.loc[index, 'quantity'] = display_label(key)
                if is_power(key):
                    output.loc[index, 'value'] = float(frame.loc[index, 'value']) / 1000.
                    if 'unit' in output:
                        output.loc[index, 'unit'] = 'kW'
    return output.rename(columns={key: display_label(key) for key in output.columns})


def dominant_states(value):
    """Translate identifiers, retaining exact participation values and unknowns."""
    if not isinstance(value, str):
        return value
    parts = []
    for part in value.split(';'):
        name, separator, weight = part.strip().partition(':')
        parts.append(label(name) + separator + weight if separator else part.strip())
    return '; '.join(parts)
