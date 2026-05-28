@echo off
chcp 65001 >nul
title 闲鱼登录 - 获取Cookie

echo ========================================================
echo   闲鱼登录 - 自动获取 Cookie
echo ========================================================
echo.
echo 操作步骤：
echo   1. 浏览器自动打开闲鱼登录页
echo   2. 扫码或输密码登录
echo   3. 登录后按 F12 - Console - 粘贴弹出的代码 - 回车
echo   4. Cookie 自动保存
echo.
echo   （全程不需要手动复制 Cookie！）
echo ========================================================
echo.

set /p ACC_ID="账号 ID（直接回车默认为 main）: "
if "%ACC_ID%"=="" set ACC_ID=main
set /p ACC_NAME="备注名（可选，直接回车跳过）: "

echo.
echo 正在启动...
D:\ruanjians\python\python.exe "E:\xianyu-ai-tool\scripts\login_auto.py" %ACC_ID% %ACC_NAME%

echo.
pause
