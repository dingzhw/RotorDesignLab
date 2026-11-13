# RotorDesignLab｜旋翼设计台

面向无人直升机概念与初步方案设计的本机计算工作台。提供孤立旋翼性能、主尾桨悬停预算、整机六分量配平、速度/质量/重心比较及通用低频开环分析；保留 Julia UH‑60 80 kt 配平、频响与短时响应基准。

[GitHub 仓库](https://github.com/dingzhw/RotorDesignLab) · [v0.1.0 发布](https://github.com/dingzhw/RotorDesignLab/releases/tag/v0.1.0) · [公开数据验证路线](docs/public-validation.md)

已发布v0.3.0整机配平。当前开发版 `0.4.0.dev1` 新增“通用开环操稳”：6自由度机体、动态入流与准定常挥舞，导出A/B、模态、频响和小扰动响应。补齐原公开主桨BT/UT高攻角、Re插值、机身/尾翼表和尾桨δ3。完整动态挥舞与桨叶惯性耦合仍待完成，尚未发布正式v0.4。[开环用法与范围](docs/open-loop.md) · [配平](docs/trim.md) · [悬停预算](docs/hover-budget.md) · [工程旋翼](docs/engineering-rotor.md) · [开发路线](docs/roadmap.md)

旋翼验证保留 [XV-15](docs/xv15-validation.md) 与 [Caradonna–Tung](docs/caradonna-tung-validation.md)：原环带模型 XV-15 同拉力功率平均低估约5.44%，C–T 同总距拉力高估约29.09%；接入旧表局部Re后仍为28.87%，真实Re气动与非局部尾迹继续排查。均匀入流核 C–T 偏差39.5%。UH‑60 与 NASA TM‑85890 姿态及部分导数作带配置差异的数学模型对照，所有通用整机结果标记为模型估算。公开参数和工程估计分别注明；已发布标签保持可复算。

## 在 Windows 上启动

需要 64 位 Python 3.14 和 Julia 1.12.4。首次准备依赖后，计算和界面可以离线运行。使用 PowerShell 从仓库根目录执行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-win64-py314.txt
julia --startup-file=no --project=julia -e 'using Pkg; Pkg.instantiate()'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

打开 [127.0.0.1:8501](http://127.0.0.1:8501)。如 `julia` 未加入 PATH，请把 `ROTOR_DESIGN_JULIA` 设为 Julia 1.12.4 的可执行文件绝对路径。网页仅监听本机地址。浏览器选择算例后点 **运行工况**，图表下方可下载完整工况与结果。UH‑60 首次运行需要等待 Julia 启动和编译。

Windows 应用执行别名有时会显示 `julia.exe`，但实际无法启动。先用 `julia --version` 检查；失败时使用真实安装路径。例如默认 Juliaup 安装可在当前 PowerShell 会话中运行：

```powershell
$env:ROTOR_DESIGN_JULIA = Join-Path $env:USERPROFILE '.julia\juliaup\julia-1.12.4+0.x64.w64.mingw32\bin\julia.exe'
& $env:ROTOR_DESIGN_JULIA --version
& $env:ROTOR_DESIGN_JULIA --startup-file=no --project=julia -e 'using Pkg; Pkg.instantiate()'
```

实际安装在其他位置时替换该路径；后续直接调用 Julia 的检查命令也使用 `& $env:ROTOR_DESIGN_JULIA`。

## 命令行与复算

```powershell
.\.venv\Scripts\python.exe -m rotordesignlab run examples/three-blade.json --out runs/hover
.\.venv\Scripts\python.exe -m rotordesignlab run examples/uh60-80kt.json --out runs/uh60
.\.venv\Scripts\python.exe -m rotordesignlab run examples/target-thrust.json --out runs/target
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/performance-sweep.json --out runs/performance
.\.venv\Scripts\python.exe -m rotordesignlab run examples/hover/synthetic-case.json --out runs/aircraft-budget
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/hover/three-candidates.json --out runs/design-compare
.\.venv\Scripts\python.exe -m rotordesignlab run examples/trim/synthetic-case.json --out runs/trim
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/trim/mass-sweep.json --out runs/trim-compare
.\.venv\Scripts\python.exe -m rotordesignlab run examples/open-loop/synthetic-linearize.json --out runs/linearize
.\.venv\Scripts\python.exe -m rotordesignlab run examples/open-loop/uh60-response.json --out runs/response
```

解压网页导出的 ZIP 后，可将其中的 `case.json` 作为同一命令的输入。每次指定新的空目录。程序生成 `result.json` 和相应的数值 CSV。求解失败时记录原因并返回退出码 2，Julia 诊断见 `solver.log`。

批量结果使用 `batch batch.json` 复算。部分失败返回退出码 2，并保留所有点的诊断和可绘图数据；求解收敛但功率或扭矩超限时单独标记。版本1机型供孤立旋翼；版本2按用途要求主尾桨、动力、挥舞、操纵和气动部件，预算与定常配平均可省略机体惯量，动态分析要求重心惯量张量。开环工况仍用版本3，analysis取linearize或response。

- 单旋翼以 SI 为准。几何 CSV 使用 `r_over_R,chord_m,twist_deg`，从有效根部到 `r/R=1`。极曲线使用 `alpha_deg,cl,cd`。总距定义在工况的参考站，输入扭转相对该站的差值加到总距上。正轴向来流指沿推进流向，正扭矩指轴输入的驱动扭矩。
- 单旋翼采用三状态 Pitt–Peters 的轴向稳态极限，轴对称工况下两个一阶谐波为零。使用叶素力和盘面动量方程求均匀诱导速度。内置几何和极曲线是合成样例。首版覆盖固定桨叶、正推力、正轴功率和低速轴向工况。
- UH‑60 保留原模型的英制、角度与操纵量定义，字段名注明单位。配平对桨叶通过周期采样平均。频响分别输出固定方位和方位平均两种全阶线化结果。时程以配平值为初始状态，横向杆施加 2 个百分点的平滑脉冲，每个 RK4 子步求解隐式加速度。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
julia --startup-file=no --project=julia julia/check_uh60.jl
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe tests/verify_models.py reference runs/reference
.\.venv\Scripts\python.exe tests/verify_models.py rotor runs/ccblade
```

参考检查会生成原始口径和修复口径的配平残差、状态、频响及 `F/G/M/A/B`。结果和验证边界见 [验证记录](docs/validation.md)。

完成依赖准备后，可运行 `python tests/release_smoke.py runs/offline-check` 检查两类算例、结果复算和失败诊断。该脚本禁止 Python socket 连接，并设置 Julia 包管理离线模式，不修改系统网络设置。离线机器需提前备齐锁定的 Python wheels、Julia 运行时和项目所需 Julia 包。

原始 J‑GenHel 代码由 Umberto Saetti 编写，依 [MIT 许可](src/LICENSE) 使用。引用 Saetti & Horn, *Flight Simulation and Control using the Julia Language*, AIAA 2022‑2354。 [原作者仓库](https://github.com/terragord7/J-GenHel) · [论文 DOI](https://doi.org/10.2514/6.2022-2354)
