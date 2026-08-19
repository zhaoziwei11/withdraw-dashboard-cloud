@echo off
chcp 65001 >nul
title 注册承运提现看板自动推送任务

echo.
echo ============================================
echo   注册承运提现看板定时推送任务
echo ============================================
echo.
echo   即将注册两个工作日自动推送任务:
echo     - 早 09:05 (衔接本机 09:00 抓取)
echo     - 午 15:15 (衔接本机 15:10 抓取)
echo.
echo   如提示 PowerShell 执行策略限制, 本 bat 已自动绕过(-ExecutionPolicy Bypass)。
echo   运行此 bat 需要管理员权限。
echo.
pause

set "PS1=%~dp0register_dashboard_task.ps1"
if not exist "%PS1%" (
    echo [失败] 找不到注册脚本: %PS1%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

echo.
echo [完成] 按任意键关闭窗口。
pause >nul
