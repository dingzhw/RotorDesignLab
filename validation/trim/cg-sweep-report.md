# 整机配平扫描

第一轴升序续接；第二轴各组独立起算。失败点保留诊断；收敛点仍分别检查数据域、操纵和功率限制。

|工况|总体状态|方程状态|数据域|设计限制|功率 kW|俯仰 °|滚转 °|失败类别|
|---|---|---|---|---|---:|---:|---:|---|
|point-0000|converged|converged|within_implemented_steady_domain|within_supplied_limits|42.058|1.3814|-3.0728||
|point-0001|converged|converged|within_implemented_steady_domain|within_supplied_limits|41.182|1.3046|-2.8086||
|point-0002|converged|converged|within_implemented_steady_domain|within_supplied_limits|38.783|1.032|-2.4022||
|point-0003|converged|converged|within_implemented_steady_domain|within_supplied_limits|35.647|0.48901|-1.952||
|point-0004|converged|converged|within_implemented_steady_domain|within_supplied_limits|32.918|-0.28763|-1.6194||
|point-0005|converged|converged|within_implemented_steady_domain|within_supplied_limits|41.822|-0.086362|-3.3034||
|point-0006|converged|converged|within_implemented_steady_domain|within_supplied_limits|40.935|-0.1595|-3.0383||
|point-0007|converged|converged|within_implemented_steady_domain|within_supplied_limits|38.533|-0.4183|-2.6274||
|point-0008|converged|converged|within_implemented_steady_domain|within_supplied_limits|35.403|-0.92421|-2.168||
|point-0009|converged|converged|within_implemented_steady_domain|within_supplied_limits|32.692|-1.6515|-1.8178||
|point-0010|converged|converged|within_implemented_steady_domain|within_supplied_limits|41.808|-1.553|-3.5395||
|point-0011|converged|converged|within_implemented_steady_domain|within_supplied_limits|40.922|-1.6215|-3.2777||
|point-0012|converged|converged|within_implemented_steady_domain|within_supplied_limits|38.5|-1.8624|-2.864||
|point-0013|converged|converged|within_implemented_steady_domain|within_supplied_limits|35.361|-2.3285|-2.3971||
|point-0014|converged|converged|within_implemented_steady_domain|within_supplied_limits|32.66|-3.0167|-2.0334||

所有结果为模型估算。各点case.json包含实际初值和完整机型，可独立搬移复算。
performance.csv保存全部操纵与动力指标；performance/controls.png和.svg用于比较。验证范围见docs/trim.md。
