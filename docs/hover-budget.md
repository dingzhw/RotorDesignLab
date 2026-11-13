# 整机悬停功率与载荷预算

本入口用于单主旋翼＋尾桨的无地效悬停方案筛选。质量进入重量，旋翼安装进入垂向力与偏航反扭矩平衡；输入惯量暂不参与计算。

机型版本 2 见 `schemas/aircraft-v2.schema.json`。工况版本 3 使用 `model: helicopter`、`analysis: hover_budget`；其他整机任务待 v0.3/v0.4 实现。旧机型和旧工况继续读取。SI，机体系 x 前、y 右、z 下；旋转和力矩定义沿用 engineering-rotor.md。

## 模板来源

`examples/hover/synthetic.json` 全部为合成值：200 kg，主桨 R=1.1 m/三叶，尾桨 R=0.24 m/双叶、力臂1.7 m。几何/极曲线沿用原演示并补入合成尾桨。限位、转速、效率、下载和可用功率均为演示假设。

`examples/hover/uh60-public.json` 从公开 `src/H60_constants.jl`（原基准05f3872）取得主尾桨尺寸、叶片数、转速、扭转、安装点、主轴前倾3°及尾桨上倾20°。长度 ft×0.3048/in×0.0254，质量采用16000 lb×0.45359237；原代码另扣叶片质量用于机身方程，本预算总重量不重复扣除。坐标以原总重心为原点，x=(FSCG-FS)、y=BL、z=(WLCG-WL)。主桨气动根切采用 hinge+spars=3.5 ft；尾桨0.2R根切及转向是假设。

UH-60 模板的极曲线是工程估计：主桨 CL=6.5(α+2°)、CD=0.008；尾桨 CL=5.73α、CD=0.0087−0.0216α+0.4α²，角度代入弧度。斜率和系数来自原常数；延伸范围、线性升力、无失速/压缩性修正属于简化。它没有使用原完整主桨 MAT 表，不能与 Julia 原模型视为等价。两者总距均在0.75R定义，未使用原操纵杆齿比或尾桨5°偏置。

UH-60 的传动效率0.96/0.93、下载3%、附件20 kW、连续/短时轴功率曲线、120秒短时限制及操纵区间均为**工程示例**，不标作 T700 实际额定值。需用功率可作模型比较，可用功率与裕度只评价当前输入假设。每个模板的 provenance 保留上述区分；可通过 `python -m tools.prepare_hover_templates` 重建公开/合成输入。

## 预算定义

在给定转速下联立主尾桨总距，主桨下载 D=k·Tmain 沿机体+z作用于重心。各桨返回 F=T·axis、M=(hub−CG)×F−rotation_sign·Q·axis。加入重力后求 Fz=0、Mz=0；其它四个分量直接报告。主尾桨轴流模型忽略互扰和侧力引起的机体倾斜。

输入轴功率 = Pmain/ηmain + Ptail/ηtail + Paccessory。传动损失独立列出，不重复计算。高度在0–11000 m使用标准对流层温度/密度/声速；可用功率只在用户曲线覆盖区间线性插值。连续和短时余量分别报告；需求时长超过短时额定时长时，仅按连续功率检查设计限制。

预算可收敛且功率不足，两者分别显示。叶素数据越界、超范围输入、无法在操纵区间闭合也各自保留诊断。所有本阶段整机结果为模型估算，验证依据引用旋翼验证包及预算数学检查。

## 运行、扫描与复算

```powershell
.\.venv\Scripts\python.exe -m rotordesignlab run examples/hover/synthetic-case.json --out runs/budget
.\.venv\Scripts\python.exe -m rotordesignlab run examples/hover/uh60-public-case.json --out runs/public-budget
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/hover/mass-altitude.json --out runs/mass-map
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/hover/main-design.json --out runs/main-map
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/hover/tail-design.json --out runs/tail-map
.\.venv\Scripts\python.exe -m rotordesignlab batch examples/hover/three-candidates.json --out runs/compare
```

网页选择“整机悬停预算”，填写质量、高度和需求时长；专业设置提供网格和扫描值。只在提交表单后运行，实际输入在结果旁保留。单点导出 CSV/Markdown/输入；扫描另含 PNG/SVG 图。下载 ZIP 解压后，单点用 `run case.json`、扫描用 `batch batch.json`，均指定新的空输出目录。

可扫描 `mass_kg, altitude_m, main_radius_m, main_rpm, tail_radius_m, tail_rpm, tail_arm_m`；半径扫描保持实际弦长/扭转与 r/R 根切站位，尾桨力臂扫描改尾桨相对重心的后向 x 距离，保持 y/z。质量、转速互相独立。高度覆盖ISA对流层与输入动力曲线交集。最多1000点、两轴、12条分组曲线。具名方案比较最多12组。

求解采用有界、归一化的两变量最小二乘；先用默认总距，必要时从总距区间35/65/85%重新尝试。只接受有效气动域内、两个残差均≤1e-4的结果。它寻找正常正推力工作支路，未穷尽任意失速曲线上的所有根；失败应检查逐点诊断，不能作为不存在任何物理解的证明。`feasible` 仅检查输入给定的功率/扭矩及求解限位；范围、求解和限制分别保存。

## 验收记录（2026-11-13）

- 26项 Python 回归；新增主尾桨反扭矩、倾斜安装独立移轴、功率收支、时长、无解/超限、输入检查、搬移离线复算和批量失败保留。
- 两模板120/240/480叶素检查：末两级关键总量最大变化0.000220%，低于0.2%门槛；合成样例残差2.50e-14，公开模板1.31e-16。
- Ryzen 9 5900X、Windows 11、Python 3.14.3，每桨240叶素：合成/公开单点0.049/0.063秒（已导入进程内，含输入读取/快照，计时不含最后报告写出）；100点扫描36.60秒（含逐点导出与绘图）。性能测试期间同时运行了界面检查，数值作为本机测量记录。
- 100点质量/高度扫描：61点收敛、39点未闭合，收敛点中27点超给定限制。15点质量/高度图为10收敛/5失败；9点主桨图全部收敛/1超限；9点尾桨图8收敛/1失败。失败属于本轮验收覆盖对象，均有独立诊断与快照。
- Streamlit AppTest：单点、导出复算、失败恢复、三方案比较、非法扫描值及旧结果清除均通过。PNG已目视检查，SVG解析通过。离线测试阻断 Python socket.connect；未修改系统网络配置。

三方案均为200 kg海平面、600秒需求：A原方案总需用41.891 kW；B主桨1.2 m、1558.33 rpm、保持原桨尖速度，总需用39.344 kW；C尾桨0.26 m、力臂1.9 m，总需用41.391 kW。B降低主桨功率但主桨扭矩和尾桨需求略增，说明尺寸与转速应联动比较。这里只比较输入假设下的预算，尚无完整配平或结构/重量代价。

详细数据见 `validation/hover-budget/acceptance.json` 和 `three-candidates-report.md`；复核入口 `python -m tools.validate_hover --out <新目录>`，界面检查 `tests/check_hover_ui.py`。
