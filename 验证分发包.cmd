@echo off
chcp 65001 >nul
"%~dp0runtime\python.exe" -X utf8 "%~dp0offline_check.py"
if errorlevel 1 goto failed
echo 检查通过。
pause
exit /b 0
:failed
echo 请保留错误信息并联系维护人员。
pause
exit /b 1
