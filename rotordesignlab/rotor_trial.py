"""Independent rig coordinates. B is fixed forward/right/down; R is the rotor.

R columns expressed in B: Rz(yaw) Ry(pitch) Rx(roll) diag(-1,1,-1).
Angles rotate the rig, not the flow frame. No aircraft mass or mounting needed.
"""
import numpy as np
from .coordinates import vector3


def basis(angles_deg):
    roll, pitch, yaw = np.deg2rad(vector3(angles_deg, '试验姿态'))
    cr, sr, cp, sp, cy, sy = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch), np.cos(yaw), np.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx @ np.diag([-1., 1., -1.])


def motion_to_flow(motion, angles):
    return -basis(angles).T @ vector3(motion, '运动速度')


def flow_to_motion(flow, angles):
    return -basis(angles) @ vector3(flow, '桨盘来流')


def gravity(angles, g):
    if isinstance(g, bool) or not isinstance(g, (int, float)) or not np.isfinite(g) or not 0 <= g <= 30:
        raise ValueError('重力加速度须在0至30 m/s²之间。')
    return basis(angles).T @ np.array([0., 0., g])


def validate(trial, case):
    if not isinstance(trial, dict) or set(trial) != {'schema_version', 'angles_deg', 'gravity_m_s2'} or trial['schema_version'] != 1:
        raise ValueError('试验姿态资料格式无效。')
    expected = gravity(trial['angles_deg'], trial['gravity_m_s2'])
    if not np.allclose(expected, case['gravity_rotor_m_s2'], rtol=0, atol=1e-10):
        raise ValueError('试验姿态与保存的局部重力不一致，请重新应用姿态。')


def effective_flap(draft):
    if draft['case'].get('flapping_model', 'module') == 'fixed':
        return 'fixed', draft['module']['rotor'], 'rotor'
    return draft['module']['flapping']['mode'], draft['module']['flapping'], 'flap'
