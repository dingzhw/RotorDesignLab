# 参数化机型与工程旋翼

开发版本：`0.2.0.dev2`，位于 `codex/rotordesignlab`。稳定版本 `v0.1.0` 和 `main` 保留首版基准。本阶段提供统一机型输入、选定旋翼的正算与指定拉力反求，以及批量性能图。

## 从内置样例开始

在仓库根目录使用已准备的 Python 环境执行，每次指定新的空输出目录：

```powershell
.\.venv\Scripts\python.exe -m rotordesignlab run examples/engineering-rotor.json --out runs/engineering
.\.venv\Scripts\python.exe -m rotordesignlab run examples/target-thrust.json --out runs/target
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/performance-sweep.json --out runs/performance
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/target-sweep.json --out runs/target-map
```

网页选择“工程旋翼”，使用本地机型 JSON 路径和旋翼 ID，再选择正算、反求总距、反求转速或批量计算。结果页显示实际运行参数，表单提交时计算。完整结果 ZIP 包含机型、几何、翼型、工况、诊断和图表。单点解压后用 `run case.json` 复算；批量用 `batch batch.json` 复算。

`synthetic-aircraft.json` 是合成的单主旋翼布局，用于演示和数值检查。200 kg 质量、惯量与安装点均为示例值。其尾桨、机身、尾翼模型尚未定义，现阶段求解所选孤立旋翼并计算它对整机重心的载荷。

## 统一机型文件

格式见 [JSON Schema](../schemas/aircraft.schema.json) 和 [完整样例](../examples/synthetic-aircraft.json)。机型版本为 `schema_version=1, kind=aircraft`，分析工况版本为 `schema_version=2, model=aircraft_rotor`。既有 UH-60 和三片叶工况继续使用版本 1。

|字段|定义|
|---|---|
|`units`、`axes`|固定为 `SI` 和 `x_forward_y_right_z_down`：机体 x 向前、y 向右、z 向下|
|`mass_properties`|质量 kg、重心坐标 m、关于重心的机体系惯量张量 kg·m²；非对角项直接填写张量元素|
|`rotors`|旋翼列表；每项具有唯一 ID、叶片数、半径、几何、翼型、安装与工况限制|
|`position_m`、`thrust_axis_body`|桨毂坐标与正推力单位向量，和重心使用同一原点；向上的主旋翼示例为 `[0,0,-1]`|
|`rotation_sign`|`+1` 表示角速度沿推力轴按右手定则，`-1` 表示相反；机体承受的反扭矩为 `-rotation_sign × Q × thrust_axis_body`|
|`defaults`|默认 rpm、总距 deg、径向叶素数；可在工况中覆盖|
|`limits`|允许的转速、总距区间；可选轴功率 W 与驱动扭矩 N·m 上限|
|`provenance`|输入来源说明；工程数据应注明原文、页码、换算或估计依据|

几何和极曲线路径相对机型文件解析。几何列为 `r_over_R,chord_m,twist_deg`，极曲线列为 `alpha_deg,cl,cd`。总距定义在 `pitch_reference_r_over_R`：各站实际桨距等于总距加该站与参考站扭转之差。轴向来流非负，沿旋翼推进流向；推力和轴输入功率均为正。

机型入口检查未知字段、非有限值、对称正定惯量及主惯量三角关系、单位推力轴、唯一 ID 和操作区间。质量和惯量当前作为整机接口保存，安装力矩按 `r × F` 与反扭矩叠加；本阶段尚未求整机平衡。

每次运行先复制机型和引用 CSV，再使用副本求解；`input-sha256.json` 记录实际输入副本的哈希。`case.json` 保留反求要求，`solved-case.json` 保存求得的转速和总距，可直接正算复核。

## 指定拉力反求

在工程工况中添加：

```json
"target": {"thrust_n": 2000, "solve_for": "collective_deg", "bounds": [2, 24]}
```

`solve_for` 可选 `collective_deg` 或 `rpm`；另一个变量保持工况值。`bounds` 可省略，默认使用机型限制。反求变量的占位值或默认值也须满足正常输入检查。

计算先由目标拉力与轴向动量平衡求诱导速度，再搜索叶素合力满足目标的总距或转速，最后完整正算回代。旧均匀入口采样 129 点、表格/径向入口采样 65 点识别变号根，再用 Brent 法求解；内部相对拉力一致性门槛为 `1e-6`。找到多个有效根时返回诊断，要求收窄区间。有限采样不能保证发现任意复杂极曲线上的所有根或恰好相切的根，工程使用应根据正算曲线限定正常工作支路。

求解结果仍需满足原轴向模型范围：固定桨叶、均匀或径向诱导速度、给定翼型数据域、正推力和正轴功率，最终叶素攻角在给定极曲线内。正算收敛与功率/扭矩超限分开记录；`feasible` 仅表示满足已提供的操作及功率/扭矩限制。

## 批量性能图

批量文件引用一个工程工况，并通过 `axes` 给出 1 至 2 个扫描变量：`rpm`、`collective_deg`、`axial_speed_m_s`、`density_kg_m3` 或 `target_thrust_n`。第一个变量作为横轴，第二个变量形成分组曲线。采用笛卡尔积，最多 1000 个工况、12 条分组曲线。反求变量不得同时作为扫描变量。

输出 `performance.csv`、`performance.png`、`performance.svg`、输入副本和逐点结果目录。CSV 包含请求参数、实际求得的总距/转速、T/Q/P、目标残差、给定限制余量及错误信息。失败点保留在表中，曲线在失败处断开；红叉标出求解收敛但超过给定功率或扭矩限制的点。

全批收敛返回退出码 0，部分或全部求解失败返回 2。功率超限本身不会改变收敛状态；自动流程还应检查 `feasible` 或批量 `limit_violations`。

## 本阶段验证记录

2026-11-13，Windows x64、Python 3.14.3，新增 Matplotlib 3.10.8 及 5 个必要依赖，安装包与官方 PyPI SHA-256 核对，项目环境 `pip check` 通过。

|检查|结果|
|---|---|
|单元与集成检查|11 项通过，覆盖 0/25 m/s 正算回代、两种反求、多解、无解、非法机型、积分/功率关系、移轴/旋转符号、输入哈希和目录搬移复算|
|单点示例|1700 rpm、2000 N 悬停：总距 `12.9355351509°`，Q=`204.370932267 N·m`，P=`36.382845767 kW`，相对拉力残差约 `1.1e-15`|
|30 点正算扫描|30 点收敛，7 点超过给定限制；高总距下合成极曲线进入失速段，拉力曲线出现峰值|
|15 点同拉力扫描|11 点收敛；1400 rpm 的 2000/2500/3000 N 和 1700 rpm 的 3000 N 在给定区间内未找到有效解，4 条诊断保留|
|批量导出复算|含成功、失败和超限点的测试批次，搬移目录后 CSV 字节一致|
|Streamlit AppTest|反求总距/转速、单点导出复算、不可达目标报错及恢复、30/15 点批量与下载入口均通过；需要本机回环 socket|

复核命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe tests/check_engineering_ui.py
```

本次保持原动力学与单旋翼气动方程。新增检查属于数值一致性和软件流程验证。公开试验验证依 [公开数据路线](public-validation.md) 开展：先补齐展向翼型、Mach/Re 数据和基准输入，再分别报告 XV-15 耗功、Caradonna–Tung 径向载荷和轴向性能的偏差。

后续整机工作包与验收见 [总体设计路线](roadmap.md)。本页的版本 1 机型与孤立旋翼结果保持原定义。
