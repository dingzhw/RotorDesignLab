# 悬停方案比较

数据为各方案实际运行输入；半径变化保持弦长/扭转及 r/R 站位。
Fz/Mz 闭合，其它力和力矩见各点结果；所有点均为模型估算。

|编号/方案|求解|限制|主桨 kW|尾桨 kW|传动损失 kW|附件 kW|总需求 kW|时长余量 kW|尾桨 N|
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
|1: A baseline|converged|within_supplied_limits|36.953|2.509|1.729|0.700|41.891|3.109|122.102|
|2: B larger main|converged|within_supplied_limits|34.442|2.574|1.629|0.700|39.344|5.656|124.150|
|3: C larger tail and arm|converged|within_supplied_limits|36.953|2.044|1.694|0.700|41.391|3.609|109.249|

CSV 保存所有参数、盘载、桨尖速度、T/Q/P、总距、限制与失败原因。
各 point 目录含实际机型、几何、翼型、工况和哈希；batch.json 支持整体搬移复算。
