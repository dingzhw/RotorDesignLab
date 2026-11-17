# RotorDesignLab｜旋翼设计台

面向无人直升机概念与初步方案设计的本机计算工作台。提供孤立旋翼性能、主尾桨悬停预算、整机六分量配平、速度/质量/重心比较及通用低频开环分析；保留 Julia UH‑60 80 kt 配平、频响与短时响应基准。

[GitHub 仓库](https://github.com/dingzhw/RotorDesignLab) · [v0.1.0 发布](https://github.com/dingzhw/RotorDesignLab/releases/tag/v0.1.0) · [公开数据验证路线](docs/public-validation.md)

2026-11-16 已完成0.4.4-A/B：速度/Mach边界、模态可靠性、错误恢复与试验性标识，以及共享扰动输入和显式下载策略。新建方案可直接选择平滑脉冲/双脉冲/阶跃并导出实际输入，旧方案保留原计算语义。0.4.5-A已接入运动速度与空气XYZ双视角及非水平姿态，旧方案保持原语义；新主桨模板使用实际机尾零方位，安装角和旋向可在页面修改；增加高度/ISA温差、kW输入、中文结果表及布局/几何/翼型预览。88项回归和页面检查通过，正式0.4.5待同事实测。[整改跟踪表](docs/reviews/RotorDesignLab-v0.4.3-评审意见回复书.md) · [开发路线](docs/roadmap.md) · [0.4.4检查](docs/v044-work.md) · [0.4.5检查](docs/v045-work.md)。软件小版本与模型成熟度分别管理，完整动态挥舞及独立操稳验证仍待完成。

已发布v0.3.0整机配平。当前开发版 `0.4.5.dev4` 将总距和转速放回孤立旋翼计算页，补齐参数提示，并接入X/Y/Z三方向来流、周期变距及六分量气动载荷，保留原轴流算法。共用方案支持保存重开和四类分析。“开环初评（低频模型·试验性）”采用6自由度机体、动态入流与准定常挥舞；完整动态挥舞与桨叶惯性耦合仍待完成，尚未发布正式v0.4。[孤立旋翼三方向来流](docs/isolated-3d.md) · [网页方案用法](docs/design-workspace.md) · [环境与预览](docs/environment-and-previews.md) · [易用性迭代计划](docs/usability-plan.md) · [开环用法与范围](docs/open-loop.md) · [配平](docs/trim.md) · [悬停预算](docs/hover-budget.md)

旋翼验证保留 [XV-15](docs/xv15-validation.md) 与 [Caradonna–Tung](docs/caradonna-tung-validation.md)：原环带模型 XV-15 同拉力功率平均低估约5.44%，C–T 同总距拉力高估约29.09%；接入旧表局部Re后仍为28.87%，真实Re气动与非局部尾迹继续排查。均匀入流核 C–T 偏差39.5%。UH‑60 与 NASA TM‑85890 姿态及部分导数作带配置差异的数学模型对照，所有通用整机结果标记为模型估算。公开参数和工程估计分别注明；已发布标签保持可复算。

## 在 Windows 上启动

**日常使用：双击根目录的 `启动旋翼设计台.cmd`。** 启动器会自动打开浏览器，无需输入网址或终端命令。中文控制窗口可以最小化；点击“停止服务并退出”会关闭本次服务，浏览器标签页可自行关闭。重复双击会打开同一工作台；端口占用时自动使用空闲端口。也可运行一个命令：`.\.venv\Scripts\pythonw.exe launch.py`。

首次部署由维护人员准备64位Python 3.14项目环境；Julia 1.12.4仅原UH-60基准入口需要，Python旋翼和通用整机模块可独立运行。安装包尚未包含在本开发版中；已有项目环境可直接双击。缺环境时启动器会提示，服务日志位于`runs/launcher/server.log`。启动仅监听本机，默认不收集框架使用统计。以下为**首次环境准备**命令：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-win64-py314.txt
julia --startup-file=no --project=julia -e 'using Pkg; Pkg.instantiate()'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

手工运行Streamlit时打开 [127.0.0.1:8501](http://127.0.0.1:8501)；使用双击启动器时以其自动打开的地址为准。如 `julia` 未加入 PATH，请把 `ROTOR_DESIGN_JULIA` 设为 Julia 1.12.4 的可执行文件绝对路径。网页从模板建立方案，在“详细设置”填写参数，选择分析任务后点 **运行分析**；可保存、重开或下载便携方案。日常入口为孤立旋翼、整机悬停预算、整机配平、开环初评（低频模型·试验性）。原 Julia UH‑60 80 kt 位于左侧“基准验证（高级）”，首次运行需等待 Julia 启动和编译。

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
