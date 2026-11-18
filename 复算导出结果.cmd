@echo off
chcp 65001 >nul
if exist "%~dp0runtime\pythonw.exe" goto portable
if not exist "%~dp0.venv\Scripts\pythonw.exe" goto missing
start "" "%~dp0.venv\Scripts\pythonw.exe" -X utf8 "%~dp0replay_results.py"
exit /b 0
:portable
start "" "%~dp0runtime\pythonw.exe" -X utf8 "%~dp0replay_results.py"
exit /b 0
:missing
echo 未找到项目运行环境，请使用完整离线包。
pause
exit /b 1
