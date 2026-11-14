# 中文展示图

2026-11-15。将既有公开基准的坐标、标题和图例改为中文；SVG 包含字形路径，便于直接查看和插入报告。专名、符号及标准单位保留。

- [XV-15 同拉力功率对照](xv15.svg)：复用 `validation/xv15/results/comparison.csv` 和 `checks.json`，通过 `tools/validate_xv15.py` 的 `--plot-only` 路径生成。
- [Caradonna–Tung 径向载荷对照](caradonna-tung.svg)：通过 `tools/validate_caradonna.py` 重跑；comparison、grid、sensitivity 三份 CSV 与原归档逐字节一致。
- [UH-60 80 kt 论文图 3 对照](uh60-figure3.svg)：`tests/compare_figure3.py` 使用本地既有 legacy/corrected 矩阵生成；comparison.csv 与归档逐字节一致。参考来源与误差结论见 [验证记录](../../docs/validation.md)。

原目录中的历史图不覆盖。此次是展示更新；数值方法、试验资料及原误差结论保持原有口径。操作与检查见 [本轮记录](../../docs/v041-usability-checks.md)。
