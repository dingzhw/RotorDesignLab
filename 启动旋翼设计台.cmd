@echo off
chcp 65001 >nul
if exist "%~dp0runtime\pythonw.exe" goto portable
if not exist "%~dp0.venv\Scripts\pythonw.exe" goto missing
start "" "%~dp0.venv\Scripts\pythonw.exe" -X utf8 "%~dp0launch.py"
exit /b 0
:portable
start "" "%~dp0runtime\pythonw.exe" -X utf8 "%~dp0launch.py"
exit /b 0
:missing
echo 未找到项目运行环境 .venv。
echo 请联系维护人员按 README 准备环境，再双击此文件。
echo 首次环境准备完成后，日常使用无需输入命令。
pause
exit /b 1
