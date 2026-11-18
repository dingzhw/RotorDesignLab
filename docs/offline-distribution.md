# 现代 Windows 离线分发与维护

本包服务无人直升机总体与初步方案分析。离线交付采用“完整目录＋本地运行时”，使用者解压后双击，无需安装 Python、填写命令或输入网址。源码开发环境继续使用 `.venv`，原有工况、模块、装配与历史结果语义保持。

## 分发内容和范围

- Python 3.14.3 AMD64、本项目锁定的科学计算和网页依赖；运行时路径独立，不调用系统 Python、用户 site-packages 或外部 PYTHONPATH。
- 中文启动器、结果 ZIP 复算窗口、完整性校验、公开模板、来源审核、中文表格与说明。网页仅监听 `127.0.0.1`，关闭框架用量统计。
- `distribution-manifest.json` 记录构建基线、未提交文件范围和每个交付文件的 SHA-256；ZIP旁另有整包 `.sha256`。提交前构建的候选包以文件哈希标识具体内容，不能仅凭基线提交号当作该提交的干净构建。
- `DEPENDENCIES.json` 记录锁定包版本及许可文件位置；保留 Python LICENSE、依赖自带许可和 `LICENSE-J-GenHel.txt`。来源数据及模型说明见 `docs/template-audit.md` 与相关公开验证文档。
- 不收录用户 `private/`、运行 `runs/`、Git目录、虚拟环境、凭据和未跟踪评审原稿。Julia原算例代码保留，但Julia运行时不在包内，日常Python任务可独立使用。

本轮验证机器为 Windows 11 x64，构建环境 Python 3.14.3。Windows 10及其他同事电脑仍需按验收表实测，不将本机检查写成所有Windows版本均通过。Win7/Python 3.8仍为后续分支。运行时沿用现有锁定版本，构建过程不联网安装或升级依赖。

## 使用与更新

先看根目录 `先读我.txt`；完整操作及待填写的实测表见[同事验收流程](colleague-acceptance.md)。选择本机可写目录，完整解压；勿在ZIP预览中双击或只复制几个脚本。首次双击 `验证分发包.cmd` 核对哈希和模块可用性；新增用户方案和运行历史不计入原包哈希。校验成功只说明交付文件一致，数值/物理验证另看各工况。

`启动旋翼设计台.cmd` 优先使用包内 `runtime/pythonw.exe`，源码工作区则使用原 `.venv`。服务就绪后自动打开浏览器，控制窗口可最小化；停止按钮仅停止该窗口拥有的服务。端口占用时自动改用其他本机端口。

下载结果 ZIP 后双击 `复算导出结果.cmd`。窗口将包解到新的 `runs/replay/日期-随机编号/input`，调用与网页、CLI相同的Python求解入口，将新结果保存至 `calculation`。`replay-check.json` 记录新旧版本、状态和汇总逐值比较。求解失败仍保留诊断；不同代码/模型版本造成的差异须按模型定义和数值容差分析，不能自动升级旧输入。摘要相同也不是独立物理验证。

维护人员更新时：

1. 关闭服务及复算窗口，备份旧目录中的 `private/`、`runs/` 和下载的方案/结果包；保留旧程序目录以便旧版本复算。
2. 将新版解压到另一个目录并执行校验。优先通过旧版网页导出、新版网页导入方案；需要保留完整库历史时，在新目录尚无用户数据的前提下复制旧 `private/`，不能合并覆盖同名方案。
3. 新版运行另建结果；复核同一旧方案的实际输入、有效模型、结果与限制。用户确认后再采用新版。旧包及失败记录继续留存。
4. 分发包不含自动更新、依赖在线安装或遥测开关变更。需要换运行时或依赖时，由维护人员单独构建、验证和交付。

## 维护人员构建与检查

在已批准并按 `requirements-win64-py314.txt` 锁定的本地项目环境中，先审阅并暂存本包源码及文档。构建器只选Git索引列出的允许目录文件；未跟踪文件即使在相同目录也不进入包。构建输出目录必须不存在：

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/build_offline.py --out runs/c3-20261118/distribution/RotorDesignLab-win64-c3
```

构建器复制实际 CPython 标准库、DLL、Tcl/Tk和依赖，生成隔离路径文件，再计算哈希和ZIP；不会将原venv的绝对路径配置作为可搬移环境。构建后在不同的中文含空格目录解压，使用包内解释器检查：

```powershell
.\runtime\python.exe -X utf8 offline_check.py
.\runtime\python.exe -X utf8 -m unittest discover -s tests -p test_offline_delivery.py -v
.\runtime\python.exe -X utf8 -c "import runpy,sys; sys.path.insert(0,'tests'); runpy.run_path('tests/check_offline_ui.py',run_name='__main__')"
.\runtime\python.exe -X utf8 tests/check_launcher.py
```

记录原始命令、退出码、运行时/硬件、包哈希及可公开检查摘要。脚本中的原生窗口操作与网页AppTest属于自动软件检查，浏览器打开回调可被替代捕获；同事实际双击、看图、填写和故障恢复另行签收。隔离网络验证仅阻止测试进程访问非本机地址，不修改Windows网络或安全设置。

常见问题：缺 `runtime` 表示包未完整解压；哈希不符先保留该包和报告并重新核对交付副本；无写权限则换到用户可写目录。服务问题保留 `runs/launcher/server.log`，复算问题保留相应 `error.txt` 与输入ZIP。不要通过关闭安全软件或覆盖用户库来排查。

本轮自动检查摘要见[公开记录](../validation/offline/checks.json)。最终分发ZIP旁提供本次提取、运行检查与整包SHA-256；公开记录中的probe哈希标识初轮检查包，不能用于校验最终交付ZIP。
