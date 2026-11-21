@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/4] 创建 Python 3.11 虚拟环境...
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv ".venv"
    if errorlevel 1 goto :failed
)

echo [2/4] 升级 pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/4] 安装 OCR、OpenCV 和桌面界面依赖...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt" ^
    -i "https://pypi.tuna.tsinghua.edu.cn/simple"
if errorlevel 1 goto :failed

if /I "%~1"=="--gpu" (
    echo [4/4] 安装 PaddlePaddle GPU 版本...
    ".venv\Scripts\python.exe" -m pip install "paddlepaddle-gpu==3.4.0" ^
        -i "https://www.paddlepaddle.org.cn/packages/stable/cu129/"
) else (
    echo [4/4] 安装 PaddlePaddle CPU 版本...
    ".venv\Scripts\python.exe" -m pip install "paddlepaddle==3.3.1"
)
if errorlevel 1 goto :failed

echo.
echo 安装完成。需要 GPU 加速时可重新运行：
echo     install.bat --gpu
pause
exit /b 0

:failed
echo.
echo 安装失败，请检查网络连接和上方错误信息。
pause
exit /b 1
