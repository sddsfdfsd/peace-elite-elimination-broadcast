@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist ".venv\Scripts\pythonw.exe" (
    echo 尚未安装运行环境，正在打开安装程序...
    call "install.bat"
    if not exist ".venv\Scripts\pythonw.exe" exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "metro_capture_app.py" %*
exit /b 0
