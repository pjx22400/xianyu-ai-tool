@echo off
chcp 65001 >nul
cd /d E:\xianyu-ai-tool
echo.
echo ╔════════════════════════════════╗
echo ║   闲鱼 AI 智能助手 v0.1.0      ║
echo ╚════════════════════════════════╝
echo.
echo [1] 启动服务
echo [2] 登录闲鱼（获取 Cookie）
echo [3] 安装依赖
echo [0] 退出
echo.
set /p choice=请选择:

if "%choice%"=="1" goto start
if "%choice%"=="2" goto login
if "%choice%"=="3" goto install
if "%choice%"=="0" goto end

:start
echo.
echo 正在启动服务...
echo 访问地址: http://localhost:8000
echo.
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
goto end

:login
echo.
echo 正在打开浏览器...
python scripts/login.py
pause
goto menu

:install
echo.
echo 安装依赖...
pip install -r requirements.txt -q
echo.
echo 安装 Playwright 浏览器...
playwright install chromium
echo.
echo 完成！
pause
goto menu

:end
