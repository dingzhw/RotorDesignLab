# 同一任务下的三方案比较

同一飞行质量、速度、高度、空气环境及维持时间的稳态方案比较；不自动评价最优方案。几何变化不自动更新质量矩/惯量，尺寸方案尚需结构与重量复核。全部结果为低阶模型估算；接近的差值应结合输入不确定性判断。开环排序仍受R19限制。

## 共用任务

飞行质量：200 kg。
- 水平速度 / (m/s)：15。
- 爬升率 / (m/s)：0。
- 高度 / m：0。
- 维持时间 / s：600。
- 径向叶素数：80。
- 方位站数：36。
- 实际空气密度 1.225 kg/m³，声速 340.294 m/s，动力黏度 1.7893e-05 Pa·s。

## 功率与状态

|方案|求解|支持范围|设计限制|主桨气动轴功率_kW|尾桨气动轴功率_kW|主桨传动损失_kW|尾桨传动损失_kW|附件耗功_kW|动力侧需用轴功率_kW|额定口径|所用可用功率_kW|本次持续时间功率余量_kW|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|基准方案|已收敛|在当前支持范围|满足给定限制|30.0183|1.58469|1.25076|0.119278|0.7|33.6731|连续|45|11.3269|
|主桨加大5%|已收敛|在当前支持范围|满足给定限制|28.7297|1.48431|1.19707|0.111722|0.7|32.2228|连续|45|12.7772|
|主桨降速5%|已收敛|在当前支持范围|满足给定限制|30.1532|1.72455|1.25638|0.129805|0.7|33.9639|连续|45|11.0361|

## 设计参数

|方案|飞行质量_kg|重心X_m|主桨半径_m|主桨转速_rpm|主桨实度|主桨盘载_N_m2|主桨旋转桨尖Mach|主桨局部最大Mach|尾桨半径_m|尾桨转速_rpm|尾桨纵向力臂_m|主桨传动效率|尾桨传动效率|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|基准方案|200|0|1.1|1700|0.0762859|518.638|0.575461|0.617423|0.24|7500|1.7|0.96|0.93|
|主桨加大5%|200|0|1.155|1700|0.0726532|470.307|0.604234|0.6459|0.24|7500|1.7|0.96|0.93|
|主桨降速5%|200|0|1.1|1615|0.0762859|518.577|0.546688|0.588839|0.24|7500|1.7|0.96|0.93|

## 配平与操纵余量

|方案|滚转角_deg|俯仰角_deg|主桨总距_deg|主桨总距到下限_deg|主桨总距到上限_deg|主桨cos周期变距_deg|主桨cos周期变距到下限_deg|主桨cos周期变距到上限_deg|主桨sin周期变距_deg|主桨sin周期变距到下限_deg|主桨sin周期变距到上限_deg|尾桨总距_deg|尾桨总距到下限_deg|尾桨总距到上限_deg|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|基准方案|-2.04921|-0.939732|11.6992|9.69923|12.3008|1.80997|16.81|13.19|-2.55699|12.443|17.557|12.0159|10.0159|11.9841|
|主桨加大5%|-1.97704|-0.996752|9.94474|7.94474|14.0553|1.7043|16.7043|13.2957|-2.11415|12.8859|17.1141|11.577|9.57701|12.423|
|主桨降速5%|-2.17857|-0.876807|13.026|11.026|10.974|1.88325|16.8832|13.1168|-3.04088|11.9591|18.0409|12.6013|10.6013|11.3987|

## 来源、假设与失败记录

### 基准方案

候选来源：复用B包200 kg合成机的冻结输入；全部参数是流程演示与工程估计，无实测整机精度依据。
几何规则：保持实际弦长与扭转；未自动更新；仅作气动/配平设计比较。
原装配来源：Synthetic example; no measured aircraft data; v0.4.4 template: six-DOF residual download=none; original public-helicopter template retained. v0.4.5: main azimuth zero points aft; original templates unchanged.
质量惯量来源：Synthetic rigid-body inertia estimate; not measured, symmetric tensor in body axes
旋翼来源：{'main': 'Same synthetic geometry and polar as v0.1.0；本次候选：复用B包200 kg合成机的冻结输入；全部参数是流程演示与工程估计，无实测整机精度依据。', 'tail': 'Synthetic: all dimensions, rpm, limits and installation estimated；本次候选：复用B包200 kg合成机的冻结输入；全部参数是流程演示与工程估计，无实测整机精度依据。'}
动力来源：Synthetic shaft-power curves, losses and 120 s rating; not a specific engine
动力按连续额定 45 kW判断；短时限时 120 s。
配平入流为稳态三状态模型、无附加尖损失；残余下载策略：none。
实际机型/几何/工况与诊断：`candidate-1/`。

### 主桨加大5%

候选来源：相对基准仅将主桨半径增加5%，保留实际弦长及扭转、总质量和质量矩；用于固定飞行质量下的气动敏感性分析，需另行复核结构与重量。
几何规则：保持实际弦长与扭转；未自动更新；仅作气动/配平设计比较。
原装配来源：Synthetic example; no measured aircraft data; v0.4.4 template: six-DOF residual download=none; original public-helicopter template retained. v0.4.5: main azimuth zero points aft; original templates unchanged.
质量惯量来源：Synthetic rigid-body inertia estimate; not measured, symmetric tensor in body axes
旋翼来源：{'main': 'Same synthetic geometry and polar as v0.1.0；本次候选：相对基准仅将主桨半径增加5%，保留实际弦长及扭转、总质量和质量矩；用于固定飞行质量下的气动敏感性分析，需另行复核结构与重量。', 'tail': 'Synthetic: all dimensions, rpm, limits and installation estimated；本次候选：相对基准仅将主桨半径增加5%，保留实际弦长及扭转、总质量和质量矩；用于固定飞行质量下的气动敏感性分析，需另行复核结构与重量。'}
动力来源：Synthetic shaft-power curves, losses and 120 s rating; not a specific engine
动力按连续额定 45 kW判断；短时限时 120 s。
配平入流为稳态三状态模型、无附加尖损失；残余下载策略：none。
实际机型/几何/工况与诊断：`candidate-2/`。

### 主桨降速5%

候选来源：相对基准仅将主桨转速降低5%；本冻结装配尾桨采用独立给定转速，不假定存在主尾桨固定速比。其余参数保持基准。
几何规则：保持实际弦长与扭转；未自动更新；仅作气动/配平设计比较。
原装配来源：Synthetic example; no measured aircraft data; v0.4.4 template: six-DOF residual download=none; original public-helicopter template retained. v0.4.5: main azimuth zero points aft; original templates unchanged.
质量惯量来源：Synthetic rigid-body inertia estimate; not measured, symmetric tensor in body axes
旋翼来源：{'main': 'Same synthetic geometry and polar as v0.1.0；本次候选：相对基准仅将主桨转速降低5%；本冻结装配尾桨采用独立给定转速，不假定存在主尾桨固定速比。其余参数保持基准。', 'tail': 'Synthetic: all dimensions, rpm, limits and installation estimated；本次候选：相对基准仅将主桨转速降低5%；本冻结装配尾桨采用独立给定转速，不假定存在主尾桨固定速比。其余参数保持基准。'}
动力来源：Synthetic shaft-power curves, losses and 120 s rating; not a specific engine
动力按连续额定 45 kW判断；短时限时 120 s。
配平入流为稳态三状态模型、无附加尖损失；残余下载策略：none。
实际机型/几何/工况与诊断：`candidate-3/`。

数值收敛、支持范围、设计限制及验证依据分别判断；失败不记为零功率。
表内实度按实际桨根切除后的桨叶平面面积/名义桨盘面积定义；局部最大Mach不等同于旋转桨尖Mach。
本轮固定飞行质量用于比较气动/动力趋势；尚未评估尺寸变化后的结构重量、制造、成本与完整任务性能。
batch.json可整体搬移复算；各candidate/run/case.json可独立复算；不修改模块库或基准装配。
