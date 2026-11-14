# 中文图表与双击启动检查

2026-11-15，`0.4.1.dev1`，Windows / 项目 `.venv` / Python 3.14。对应[易用性计划](usability-plan.md)第一轮；计算模型沿用 `0.4.0.dev1` 的适用范围和验证状态。

## 本轮交付

- 根目录 `启动旋翼设计台.cmd`：使用项目已有环境，弹出中文控制窗口，服务就绪后自动打开本机网页。可最小化窗口，关闭窗口或点击“停止服务并退出”结束本次服务。重复启动复用相同目录的运行实例；不结束占用端口的其他程序。
- 工程旋翼、悬停预算、配平扫描、开环模态/频响/响应，以及 XV-15、C–T、UH-60 论文图 3 的绘图文字使用中文。保留物理符号、专名和标准单位；网页原有单旋翼与 UH-60 交互图的轴标题已为中文。
- Matplotlib 统一选择已安装中文字体；本机使用 Microsoft YaHei。SVG 保存字形路径，转发不依赖接收方安装该字体。找不到中文字体时给出明确提示。
- 不改变求解方程和输入格式。统一详细设置、方案管理和 Excel/CSV/TXT 导入按计划后两轮实施。

## 已执行检查

|检查|结果与证据|
|---|---|
|启动器依赖与缺环境提示|缺少 Streamlit 时给中文错误；无 `.venv` 的中文/空格目录执行 CMD，返回 1 并显示维护提示|
|服务生命周期|端口占用时另选端口；按目录识别实例；本机健康检查成功；停止后进程退出、状态文件清除|
|原生控制窗口|真实 Tk 窗口等待服务就绪，触发浏览器打开回调，点击停止按钮后服务退出；测试替换浏览器回调，没有代替同事实际双击试用|
|工程旋翼回归|`test_engineering.py`：8 项通过，包含正反求、快照及批量结果|
|悬停预算批量回归|`test_hover_batch.py`：2 项通过，包含目录搬移、失败及限制显示|
|配平批量回归|`test_trim_batch.py`：2 项通过，包含续接、部分失败与离线复算|
|图形检查|生成四类产品图，以及三套公开基准对照图；实际查看开环频响、配平性能、XV-15、C–T、论文图 3 的 PNG，文字、单位、符号及布局正常；检查发布的 SVG 字形路径|
|数值未变|C–T 重跑的 comparison/grid/sensitivity 三份 CSV 与归档逐字节一致；图 3 从既有矩阵重算的 comparison.csv 与归档逐字节一致；XV-15 直接复用归档 comparison.csv/checks.json 重绘|

工作目录均为仓库根目录。主要复算命令：

```powershell
.venv\Scripts\python.exe tests/check_launcher.py
.venv\Scripts\python.exe -m unittest discover -s tests -p test_engineering.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -p test_hover_batch.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -p test_trim_batch.py -v
.venv\Scripts\python.exe -m tools.validate_caradonna --out runs/ux-041-ct
```

直接执行 tests 下的脚本时，将仓库根目录加入该进程的 `PYTHONPATH`。图 3 使用本机已有的 `C:\Python314\python.exe`（含 PyMuPDF），执行 `tests/compare_figure3.py docs/2022_Saetti_Horn_SciTech.pdf runs runs/ux-041-figure3`；读取 `runs/legacy` 与 `runs/corrected` 的既有矩阵，不重新运行 Julia。PDF 仍为本地资料，未纳入此次提交。

本地检查日志：`runs/ux-041-launcher.log`、`runs/ux-041-engineering.log`、`runs/ux-041-hover-batch.log`、`runs/ux-041-trim-batch.log`。改动前文件及 SHA-256 位于 `runs/ux-041-backup`。当前产品图检查产物位于 `runs/ux-041-plots`；其中旋翼三个示意点只用于检查绘图，其余使用既有公开 UH-60 结果，均不作为新的物理验证。

## 使用边界与后续验收

日常启动已简化；首次部署仍由维护人员按 README 准备项目环境。本轮没有制作安装包，也没有完成新同事的实际试用。新环境安装、完整断网交付、Excel 往返及无 JSON 的完整建模流程，在第三轮统一验收。现阶段可先在本机双击体验，再进入第二轮的统一机型详细设置。

三套中文基准图见 [展示图说明](../validation/presentation/README.md)。原验证数值与历史图仍保留在原目录；更新中文图不改变其科学结论。
