# 公开数据验证路线

核查日期：2026-11-13。面向孤立旋翼、整机配平和操稳评估。来源细目、获取状态和限制见 [来源索引](public-validation-sources.json)。

## 优先采用的数据

|顺序|对象|已找到的材料|接入前的工作|
|---|---|---|---|
|1|XV-15 原金属桨悬停|NASA Betzina 2002 试验；NASA/TP-2004-212262 附录 A 工程几何和气动输入 [S01、S02]|核对桨型、参考总距、预锥、马赫数和桨毂扣除；支持展向翼型及 Mach 查表后再运行正式对照|
|2|Caradonna–Tung 悬停旋翼|NASA-TM-81232 压力与尖涡试验 [S03]|选亚声速点，重建几何和工况，将压力积分为叶素模型可比较的径向载荷|
|补充|UIUC 螺旋桨|静态转速扫描、轴向来流扫描、部分近似几何的文本数据 [S04]|先选择同时有几何和性能文件的桨；核对翼型与 Reynolds 数，采用网站已修正版本|
|整机|UH-60|NASA-TM-85890 配置与数学模型；Airloads 飞行/风洞报告目录 [S05、S06]|先做配置和配平回归，再选报告中可恢复工况的实测量；完整原始数据库的直接下载尚未确认|
|后续耦合|桨翼、前后翼|NASA-TM-88255；Auburn Shah 2023 [S07、S08]|分别检验下载和分翼载荷；等对应模块形成后接入|

现阶段选 XV-15 作为首个耗功验证目标，Caradonna–Tung 作为独立径向载荷检查，UIUC 作为轴向工况补充。三者分别覆盖不同尺度和观测量，误差分别报告。BO-105 的独立飞行动力学研究已找到索引，但该 NTRS 记录没有全文下载，保留为后续候选 [S09]。

## 如何建立可复算的验证包

1. 保存原始公开文献、URL、下载日期与 SHA-256；图表读取另存校准坐标、来源页和数字化误差。公开 Git 仓库保存来源清单和提取脚本，下载文件默认放在忽略目录。
2. 为每个试验建立独立机型和工况。记录几何、翼型、转速、密度、速度、桨距定义、坐标和力矩参考点；区分原文值、单位换算值与估计值。
3. 先固定输入完成单位、符号、积分和离散检查，再做预测对照。若用某些试验点标定参数，另留独立点检查，记录标定参数及数据范围。
4. 旋翼同时报告同总距的 T/Q 和同拉力的 Q/P；参考曲线只在覆盖区间内插值。保存失败点，不以删除失败点改善误差统计。
5. 各种结果标注为解析核查、实现互校、试验曲线对照或原始试验数据对照。每一类均记录工况范围、偏差和未闭合的问题。

这一流程沿用已有部件与干扰验证工作的经验：几何和口径先一致，分项载荷与总量同时检查；时间步、空间网格和尾迹设置分别改变；直接试验、二次数字化和方法互校分别记录。既有其他项目的数值误差不转写成本工具的验证结果。

## 比较量与模型边界

- 旋翼系数采用 `CT=T/(ρ A (ΩR)²)`、`CQ=Q/(ρ A (ΩR)² R)`、`CP=P/(ρ A (ΩR)³)=CQ`。悬停 `FM=CT^(3/2)/(√2 CQ)`。UIUC 的 `n,D` 系数必须先换算，保留原始列。
- 当前轴向求解器只有单一随攻角变化的极曲线和均匀诱导速度。XV-15 的完整工程输入需要展向/Mach 气动表；暂不把简化替代翼型算出的结果列作正式验证。
- Caradonna–Tung 的弦向压力与尖涡位置属于更高层次的观测量；当前叶素模型以积分载荷为目标。
- UH-60 TM-85890 中的配平及导数对照属于数学模型互校。Airloads 原始数据库与公开报告的可获取程度分别记录。
- NASA 桨翼试验可检验对应的干扰模型。仅引用经验下载公式，尚未完成该试验的复现。

## 获取与状态

运行 `python tools/fetch_public_sources.py --out runs/public-sources` 获取索引中提供直接 PDF 链接的 NASA 文献，生成下载清单和哈希；支持中断后复用已下载文件。程序计算入口不会自动联网。

本阶段完成公开来源筛选和获取路径核对。新增工程旋翼功能先通过合成输入和解析关系检查；实验精度结论在相应公开算例实际运行后追加，不预填统一百分比门槛。

## 原始来源

- S01：[Betzina 2002](https://rotorcraft.arc.nasa.gov/Publications/files/Betzina_AHS02.pdf)
- S02：[NASA/TP-2004-212262](https://rotorcraft.arc.nasa.gov/Publications/files/Acree_TP2004-212262.pdf)
- S03：[NASA-TM-81232](https://ntrs.nasa.gov/citations/19820004169)
- S04：[UIUC Propeller Database Volume 1](https://m-selig.ae.illinois.edu/props/volume-1/propDB-volume-1.html)
- S05：[NASA-TM-85890](https://ntrs.nasa.gov/citations/19840015585)
- S06：[UH-60 Airloads Flight Project](https://rotorcraft.arc.nasa.gov/Research/Programs/uh_60_program.html)；[风洞试验](https://rotorcraft.arc.nasa.gov/Research/Programs/uh_60_test_summary.html)
- S07：[NASA-TM-88255](https://ntrs.nasa.gov/citations/19860018588)
- S08：[Shah 2023](https://etd.auburn.edu/handle/10415/9101)
- S09：[BO-105 识别研究索引](https://ntrs.nasa.gov/citations/19910060770)
