# 独立旋翼模块：M1 文件和计算入口

0.4.6.dev3 已实现独立模块、命令行计算、保存与旧方案提取。网页模块库属于后续 M2，本版网页仍是原工作台。M1 不改变旧方案的计算语义，也不关闭 R19。

模块不含整机质量、重心、惯量、主尾桨角色或安装位置。`rotor`保存几何、翼型、旋向、局部操纵限制；`blade_mass`保存单片桨叶质量及关于挥舞铰的一阶/二阶质量矩；`flapping`保存预锥、铰偏置、刚度、阻尼等；`hub`保存桨毂自身的质量、局部重心和重心惯量。几何与翼型仍是CSV或原翼型表格式。

局部坐标是右手系，z沿正推力、x为零方位；不预设机头/机尾。`flow_rotor_m_s`为三个局部空气相对桨毂速度分量（m/s），正贯流时z分量为负；`gravity_rotor_m_s2`为重力在同一基底的三个分量，水平向上旋翼通常为`[0,0,-9.80665]`。试验台姿态只影响重力方向，不需要飞机位置或重量。输出六分量为气动载荷，力矩参考点是桨毂。

## 配置与保存

可读文件`module.json`遵循`schemas/rotor-module.schema.json`，相邻放`geometry.csv`和`polar.csv`或`polar.json`。`.rdlr`包包含相同数据和SHA-256清单，移动到新目录仍可计算。模块只允许包内固定数据表名称，不引用外部绝对路径。计算输出同时保存可读模块、数据表、模块包、实际工况和输入哈希。

开发接口：`rotor_module.load(path)`读取JSON或包；`pack/unpack`执行清单、哈希及结构校验；`save(module, assets, path)`以独占方式新建文件，已有文件不覆盖。资产字典的值为原始字节。M2再接入中文编辑、模块库版本及冲突恢复，普通同事届时不需要编辑JSON。

当前可直接复算两套样例：

- `examples/rotor-modules/synthetic`：合成旋翼；m₀=2.5 kg、m₁=1.5 kg·m、Iβ=1.2 kg·m²，桨毂2 kg，均明确标为合成输入。
- `examples/rotor-modules/uh60-public`：原公开部件模板提取的主旋翼，保留既有气动与质量矩来源；单片质量和桨毂独立质量属性未填，缺项在结果中集中列出。不是新增试验精度认证。

单片质量、m₁与Iβ按铰外非负质量分布检查矩约束。桨毂惯量张量检查对称、正定及主惯量三角关系。缺少当前分析不使用的质量字段可以保存；铰接挥舞缺少质量矩、刚度或阻尼则拒绝计算。当前单片m₀和桨毂质量属性仅保存，A2前不进入整机惯性耦合；`parameter_usage`和`missing_mass_data`说明实际用途与缺项。

## 计算与复算

```powershell
.venv\Scripts\python.exe -m rotordesignlab run examples/rotor-modules/synthetic/case.json --out runs/my-module-run
.venv\Scripts\python.exe -m rotordesignlab run runs/my-module-run/case.json --out runs/my-module-replay
```

模块工况使用版本4、`model: rotor_module`；`module_file`指向JSON或`.rdlr`。转速、总距、环境、来流、重力、网格及周期变距属于工况。`method=spatial`复用原方位角叶素、PP入流与稳态挥舞；`method=axial`复用原轴流性能核，只允许纯轴向、零周期变距和固定桨叶。`flapping_model=module`使用模块挥舞属性，`fixed`明确选择固定桨叶近似。目标反求复用原求根入口，配置`target`的拉力和`solve_for`。

输出包含结果JSON、中文摘要、局部载荷CSV、径向载荷、三方向方法的方位叶素数据与中文图、原工况及求解后工况。模块输入没有任何虚填的整机参数；运行器直接进入旋翼核，不调用机型读取器。能力范围沿用既有核：正推力/正功率、正贯流，三方向方法μ≤0.25且在翼型数据域内；新增文件格式不扩大物理范围。

## 旧方案提取

```powershell
.venv\Scripts\python.exe -m rotordesignlab extract-rotor examples/public-helicopter/uh60-public.json --rotor-id main --out runs/extracted-main
```

也可输入旧`.rdl`包。输出目录必须不存在，原文件只读；`migration.json`保留来源SHA、原安装基底、原位置、原参考工况和原操纵限制。安装信息只在迁移记录中，不进入独立模块。

加`--case <旧孤立旋翼工况.json>`可生成`converted-case.json`。转换限于同一旋翼的`spatial_rotor/aircraft_rotor`工况；来流和重力按原安装基底转入局部系，保留原操纵、环境和求解方法。总距、预锥、入流/尖损失等覆盖项不能悄悄丢弃；暂不能无歧义转换的物理覆盖项明确拒绝，需另存对应模块。旧整机配平不能直接当成孤立工况转换。转换后应按迁移记录核对源配置，不把旧工况套到另一架同名旋翼上。

## 本轮验证

- 独立性：将旧机型读取器替换为必报错函数，固定/铰接模块仍计算成功。
- 移动与复算：包往返、独占保存、模块快照及工况复算数值一致；篡改资产哈希被拒绝。
- 旧模型对照：公开UH-60主、尾桨采用非水平重力和三方向来流，同物理工况T/Q/P、挥舞及六分量载荷通过相对1e−6；近零载荷绝对1e−7 N或N·m、挥舞1e−8°门槛。
- 参数生效：改变弹簧或阻尼会改变求得挥舞；非法质量矩、缺少必要惯量、外部资产路径和整机字段均被拒绝。
- 轴流固定桨叶及指定拉力反求通过；完整旧回归随本包运行。过程及失败日志在`runs/m1-20261118/`。

后续先做M2中文旋翼工作区，再做M3装配和三个整机入口。当前M1不包含批量模块网页、安装实例或模块质量自动累加，A2继续后置。
