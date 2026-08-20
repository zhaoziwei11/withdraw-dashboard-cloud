@echo off
chcp 65001 >nul
title 修复承运提现定时任务

echo.
echo ============================================
echo   修复承运提现定时任务
echo ============================================
echo.
echo 本脚本会重新注册 4 个定时任务:
echo   - 09:00  抓取待提现
echo   - 09:05  推送到 GitHub 看板
echo   - 15:00  抓取失败原因 + 需求二
echo   - 15:15  推送到 GitHub 看板
echo.
echo 任务会设为"无论用户是否登录都运行"，
echo 运行时需要输入 Windows 登录密码。
echo.
echo 请右键本 bat, 选择"以管理员身份运行"。
echo.
pause

set "PS1=%~dp0fix_all_tasks.ps1"
if not exist "%PS1%" (
    echo [失败] 找不到脚本: %PS1%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

echo.
echo [完成] 按任意键关闭窗口。
pause >nul
