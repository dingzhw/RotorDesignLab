"""Physical coordinate conversions shared by UI, case adapter and sweeps."""
from copy import deepcopy
import numpy as np
from .airframe import body_to_ned
from .azimuth import rotor_basis

MOTION_AXES = ('motion_forward_m_s', 'motion_right_m_s', 'motion_climb_m_s')
FLOW_AXES = ('flow_x_m_s', 'flow_y_m_s', 'flow_z_m_s')


def vector3(value, name):
    if (not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 3 or
            any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.number)) for v in value)):
        raise ValueError(name + '需要三个有限数值。')
    array = np.asarray(value, dtype=float)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError(name + '需要三个有限数值。')
    return array


def attitude_matrix(attitude_deg=(0., 0.)):
    if (not isinstance(attitude_deg, (list, tuple, np.ndarray)) or len(attitude_deg) != 2 or
            any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.number)) for v in attitude_deg)):
        raise ValueError('姿态需要滚转、俯仰两个有限角度。')
    angles = np.asarray(attitude_deg, dtype=float)
    if not np.isfinite(angles).all() or abs(angles[0]) > 180 or abs(angles[1]) > 89:
        raise ValueError('滚转角范围±180°，俯仰角范围±89°；航向采用机头水平投影方向。')
    return body_to_ned(*np.deg2rad(angles))


def motion_to_flow(motion_m_s, attitude_deg=(0., 0.)):
    # Heading-horizontal frame: forward, right, UP. Solver input: air relative
    # to the hub in body X forward / Y right / Z down. No induced velocity here.
    motion = vector3(motion_m_s, '运动速度')
    return -attitude_matrix(attitude_deg).T @ (motion * [1., 1., -1.])


def flow_to_motion(flow_body_m_s, attitude_deg=(0., 0.)):
    return (-attitude_matrix(attitude_deg) @ vector3(flow_body_m_s, '三方向来流')) * [1., 1., -1.]


def canonical_spatial_case(case):
    """Resolve one velocity representation; snapshots store only body flow."""
    if ('flow_body_m_s' in case) == ('motion_m_s' in case):
        raise ValueError('三方向工况须且只能提供flow_body_m_s或motion_m_s其中一项。')
    result = deepcopy(case)
    attitude = case.get('attitude_deg', [0., 0.])
    attitude_matrix(attitude)
    if 'motion_m_s' in case:
        flow = motion_to_flow(case['motion_m_s'], attitude)
        result.pop('motion_m_s')
    else:
        flow = vector3(case['flow_body_m_s'], '三方向来流')
    if np.linalg.norm(flow) > 150:
        raise ValueError('来流合速度超过本入口150 m/s的输入范围。')
    result['flow_body_m_s'] = flow.tolist()
    return result


def selected_basis(selected):
    reference = selected.get('flight', {}).get('x_reference_body')
    if reference is None:
        # Historical v1 fallback is intentionally retained.
        reference = next(axis for axis in ([1, 0, 0], [0, 1, 0], [0, 0, 1])
                         if abs(np.dot(axis, selected['thrust_axis_body'])) < .99)
    return rotor_basis(selected['thrust_axis_body'], reference)


def scan_velocity(case, values):
    """Sweep axes retain their stated physical frame even if UI view changes."""
    motion_keys = set(values) & set(MOTION_AXES)
    flow_keys = set(values) & set(FLOW_AXES)
    if motion_keys and flow_keys:
        raise ValueError('同一批次不能混合运动速度与机体系来流扫描轴。')
    result = canonical_spatial_case(case)
    if motion_keys:
        motion = flow_to_motion(result['flow_body_m_s'], result.get('attitude_deg', [0., 0.]))
        for key in motion_keys:
            motion[MOTION_AXES.index(key)] = values[key]
        result['flow_body_m_s'] = motion_to_flow(motion, result.get('attitude_deg', [0., 0.])).tolist()
    for key in flow_keys:
        result['flow_body_m_s'][FLOW_AXES.index(key)] = values[key]
    return result
