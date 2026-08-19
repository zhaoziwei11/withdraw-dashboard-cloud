@echo off
chcp 65001 >nul
title 承运提现 - 同步最新数据到云端看板
set PYTHONIOENCODING=utf-8

echo.
echo ============================================
echo   承运提现日报 - 同步最新数据到云端看板
echo ============================================
echo.
echo   直接读取本机数据文件并推送到云端,
echo   不需要 8766 控制台在运行。
echo.

cd /d "%~dp0.."

"C:\Users\92893\AppData\Local\Programs\Python\Python312\python.exe" "sync\sync_to_cloud.py"

echo.
if %ERRORLEVEL% EQU 0 (
    echo [成功] 云端看板已更新, 刷新网页即可看到最新数据。
) else (
    echo [失败] 同步未成功, 请检查上方错误信息 ^(常见: 断网 / api.github.com 不可达^)。
)
echo.
pause
