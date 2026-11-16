"""Explicit residual download, separate from body/tail wake loads."""
import numpy as np


def settings(aircraft, analysis='trim'):
    configured = aircraft['hover']['download_fraction']
    policy = aircraft.get('trim', {}).get('download_policy', 'legacy_fraction')
    if policy not in ('none', 'legacy_fraction'):
        raise ValueError('download_policy须为none或legacy_fraction。')
    strategy = 'hover_fraction' if analysis == 'hover_budget' else policy
    fraction = 0. if strategy == 'none' else configured
    return dict(strategy=strategy, effective_fraction=fraction, configured_hover_fraction=configured,
                six_dof_strategy=policy, applied_at='cg',
                scope='附加残余比例力；独立于已有机身和尾翼气动载荷，无速度硬切换。',
                note=('六分量分析未附加残余下载；机身下洗/下载尚未完整建模。' if policy == 'none'
                      else '六分量分析保留历史常比例下载；该比例不具有全速域试验依据。'),
                comparison_note=('悬停预算使用经验比例，六分量分析不附加该项；比较功率前须同时核对模型差异。'
                                 if policy == 'none' else '预算和六分量分析均采用所给经验比例，载荷与配平方程仍不同。'))


def load(aircraft, main_thrust, thrust_axis):
    info = settings(aircraft)
    magnitude = info['effective_fraction'] * main_thrust
    force = -magnitude * np.asarray(thrust_axis)
    return dict(force_body_n=force.tolist(), moment_cg_body_nm=[0., 0., 0.], power_w=0.,
                magnitude_n=float(magnitude), **info)
