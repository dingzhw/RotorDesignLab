# 开发记录

## 2026-11-13 · 发布与工程旋翼阶段

- 工作目录：`C:\J-GenHel`；开发分支：`codex/rotordesignlab`；起点：`2d90bf8`。
- 用户授权：完成 v0.1.0 剩余检查、发布和仓库改名，然后开发统一机型文件、指定拉力反求、批量性能图；分阶段验证并同步 GitHub。
- 初始工作区仅有用户提供、未跟踪的论文 PDF；保留原状，不纳入公开提交。
- v0.1.0 验收沿用两类算例、图 3 量化对照和已完成的界面试用；修复模型与飞行试验的差异见 validation.md。
- 公开验证数据按原始试验、数字化曲线、模型互校分别记录，私有工程资料留在本地。
- 发布检查完成：全新 Python 虚拟环境安装 35 个官方哈希校验的 wheels，pip check、3 项 Python 回归、7 项 Julia 数值检查、两类算例离线复算与界面失败恢复通过。
- 系统 Julia 应用别名不可执行，使用已安装的 Julia 1.12.4 实际路径；AppTest 首次受沙箱回环限制阻塞，允许本机回环后通过。未改动系统配置。
- 检查命令和结果：`tests/release_smoke.py runs/release-check/offline`，退出码 0；`julia/check_uh60.jl`，7/7；`unittest discover -s tests -v`，3/3；隔离环境 AppTest，退出码 0。
- 详细发布证据见 `docs/releases/v0.1.0.md`，本地安装包和日志位于忽略的 `runs/release-check`。
- v0.1.0 已发布至提交 `5d493fe`，GitHub Release 与标签已核对；仓库改名为 `dingzhw/RotorDesignLab`，仓库 ID 保持 `794431629`，本地 origin 和 main 已同步。
- 公开来源阶段：9 条来源登记，5 份 NASA 原文下载并记录 SHA-256；优先 XV-15 悬停耗功、Caradonna–Tung 径向载荷、UIUC 轴向性能；UH-60 用于整机参数和后续对照。BO-105 全文和 Airloads 完整原始数据库未取得。
- 来源资料验证：JSON 解析、下载文件 PDF 头及哈希、下载脚本离线复用检查。现阶段没有新增试验精度结论。
- 后续：统一机型、指定拉力反求和批量性能图；完成相关测试后同步开发分支。
