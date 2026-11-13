# 通用低频开环检查

本目录为0.4.0.dev1的数值/模型互校摘要。`checks.json`记录两模板0/20m/s导数与20m/s四操纵响应检查；各子目录为A/B、E/F/G、模态和状态元数据。`tm85890-comparison.csv`保留9项公开模型导数差异，`tm85890-scope.json`记录原参考控制配置。

复算（新输出目录）：

```powershell
julia --startup-file=no julia/inflow_dynamics_check.jl validation/open-loop/julia-inflow-dynamics.csv
python -m tools.validate_open_loop --out runs/open-loop-check
python -m tools.compare_public_derivatives --out runs/derivative-check
python -m unittest discover -s tests -v
```

网页自动检查为`tests/check_open_loop_ui.py`，需要本机回环socket权限。其验证内容为表单、实际输入、CLI复算、失败恢复、导出；不代替新用户试用。参数与模型限制见`docs/open-loop.md`和`docs/v040-work.md`。

NASA来源：[TM-85890](https://ntrs.nasa.gov/citations/19840015585)，表5/6/8（印刷页16/17/19），导数说明印刷页8。1/20/40kt的Xu、Zw、Mq原表值已逐项核图。参考开启PBA及主动平尾；本版固定原始桨距、准定常挥舞且缺完整惯性耦合，所有结果保留model_estimate。既有Julia全阶模型与低频15状态模型分开使用。
