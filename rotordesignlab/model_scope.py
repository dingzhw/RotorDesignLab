"""Shared user-facing model scope and input bounds."""

OPEN_LOOP_LABEL = '开环初评（低频模型·试验性）'
SPATIAL_SCOPE = ('三方向旋翼为模型估算：已检查轴流极限、坐标协变和载荷积分；'
                 '斜流六分量载荷尚缺独立试验验证，轴流基准的精度不直接推广到斜流。')
MACH_SCOPE = ('Mach表覆盖只表示局部数据可插值；当前模型未建立跨声速、非定常失速的物理验证。')
RESPONSE_DURATION_BOUNDS = (0.05, 10.0)

COUPLING_WARNING = ('铰接旋翼开环交叉耦合待修复（R19）：桨毂传力与旋翼动量尚未闭合，'
                    '已复现异常交叉导数。矩阵、模态和响应仅供故障诊断，暂不用于稳定性判断或方案优劣排序。')


def open_loop_restriction(aircraft):
    affected = [r['id'] for r in aircraft['rotors']
                if r.get('flight', {}).get('flapping', {}).get('mode') == 'hinged']
    from .mass_partition import enabled
    note = COUPLING_WARNING
    if enabled(aircraft):
        note = ('R19整机验收尚未关闭：新模型已接通主尾桨质量分账、动态一阶挥舞及隐式加速度；'
                '公开机型质量估算、整机导数及响应仍须验收。仅供诊断，不用于稳定性判断或方案排序。')
    return dict(issue='R19' if affected else None, affected_rotors=affected,
                engineering_use_allowed=False,
                evaluation_status='cross_coupling_unresolved' if affected else 'experimental_unvalidated',
                note=note if affected else '低频模型仍属试验性，未完成独立动态验证。')
