"""Shared user-facing model scope and input bounds."""

OPEN_LOOP_LABEL = '开环初评（低频模型·试验性）'
SPATIAL_SCOPE = ('三方向旋翼为模型估算：已检查轴流极限、坐标协变和载荷积分；'
                 '斜流六分量载荷尚缺独立试验验证，轴流基准的精度不直接推广到斜流。')
MACH_SCOPE = ('Mach表覆盖只表示局部数据可插值；当前模型未建立跨声速、非定常失速的物理验证。')
RESPONSE_DURATION_BOUNDS = (0.05, 10.0)
