# 公开部件互校

来源：仓库原 `data/H60fuselage.mat`、`src/H60_constants.jl`，以及 [NASA TM-85890](https://ntrs.nasa.gov/citations/19840015585) 表1、4及模型说明。源模型不同部件的试验溯源尚不齐全。本目录记录软件/模型互校，不作为飞行试验验证。

复算（项目环境）：

```powershell
python -m tools.prepare_public_helicopter
python -m tools.validate_public_components --out runs/component-check --export-only
julia --startup-file=no julia/fuselage_check.jl runs/component-check runs/component-check/julia-fuselage.csv
python -m tools.validate_public_components --out runs/component-check
```

详细输入假设、尾桨Re范围、反向流尾翼估计及未实现项见 `docs/v040-work.md`。旧v0.3工况保留不变；本目录grid.csv仅公开UH-60参数。
