# 整机配平扫描

第一轴升序续接；第二轴各组独立起算。失败点保留诊断；收敛点仍分别检查数据域、操纵和功率限制。

|工况|总体状态|方程状态|数据域|设计限制|功率 kW|俯仰 °|滚转 °|失败类别|
|---|---|---|---|---|---:|---:|---:|---|
|point-0000|converged|converged|within_implemented_steady_domain|within_supplied_limits|35.991|-0.07844|-3.1822||
|point-0001|converged|converged|within_implemented_steady_domain|within_supplied_limits|35.146|-0.1731|-2.903||
|point-0002|converged|converged|within_implemented_steady_domain|within_supplied_limits|32.849|-0.48378|-2.4663||
|point-0003|converged|converged|within_implemented_steady_domain|within_supplied_limits|29.96|-1.076|-1.9965||
|point-0004|converged|converged|within_implemented_steady_domain|within_supplied_limits|27.593|-1.912|-1.6649||
|point-0005|converged|converged|within_implemented_steady_domain|within_supplied_limits|41.822|-0.086362|-3.3034||
|point-0006|converged|converged|within_implemented_steady_domain|within_supplied_limits|40.935|-0.1595|-3.0383||
|point-0007|converged|converged|within_implemented_steady_domain|within_supplied_limits|38.533|-0.4183|-2.6274||
|point-0008|converged|converged|within_implemented_steady_domain|within_supplied_limits|35.403|-0.92421|-2.168||
|point-0009|converged|converged|within_implemented_steady_domain|within_supplied_limits|32.692|-1.6515|-1.8178||
|point-0010|converged|converged|within_implemented_steady_domain|exceeded|48.213|-0.096381|-3.434||
|point-0011|converged|converged|within_implemented_steady_domain|exceeded|47.335|-0.14862|-3.1857||
|point-0012|converged|converged|within_implemented_steady_domain|within_supplied_limits|44.931|-0.3571|-2.8046||
|point-0013|converged|converged|within_implemented_steady_domain|within_supplied_limits|41.685|-0.78408|-2.3666||
|point-0014|converged|converged|within_implemented_steady_domain|within_supplied_limits|38.793|-1.4132|-2.0154||

所有结果为模型估算。各点case.json包含实际初值和完整机型，可独立搬移复算。
performance.csv保存全部操纵与动力指标；performance/controls.png和.svg用于比较。验证范围见docs/trim.md。
