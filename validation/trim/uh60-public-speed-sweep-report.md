# 整机配平扫描

第一轴升序续接；第二轴各组独立起算。失败点保留诊断；收敛点仍分别检查数据域、操纵和功率限制。

|工况|总体状态|方程状态|数据域|设计限制|功率 kW|俯仰 °|滚转 °|失败类别|
|---|---|---|---|---|---:|---:|---:|---|
|point-0000|converged|converged|within_implemented_steady_domain|within_supplied_limits|1307.7|4.3922|-2.386||
|point-0001|converged|converged|within_implemented_steady_domain|within_supplied_limits|1269.6|4.4327|-2.2278||
|point-0002|converged|converged|within_implemented_steady_domain|within_supplied_limits|1159.1|4.5032|-1.9104||
|point-0003|converged|converged|within_implemented_steady_domain|within_supplied_limits|1021.1|4.4382|-1.5577||
|point-0004|converged|converged|within_implemented_steady_domain|within_supplied_limits|906.27|4.1705|-1.3319||

所有结果为模型估算。各点case.json包含实际初值和完整机型，可独立搬移复算。
performance.csv保存全部操纵与动力指标；performance/controls.png和.svg用于比较。验证范围见docs/trim.md。
