# 注册「承运提现看板自动推送」定时任务
# 在已有本机抓取任务(09:00 / 15:10)之后, 自动把最新数据推送到 GitHub 看板,
# 实现本机全自动。云端 GitHub Actions 已加防护(抓取失败自动跳过推送), 与本地任务可同时运行。
#
# 用法(本机, 需管理员 PowerShell):
#   如果右键"用 PowerShell 运行"报"禁止运行脚本", 请在管理员 PowerShell 里执行:
#     powershell.exe -ExecutionPolicy Bypass -File ".\register_dashboard_task.ps1"
#   或直接用完整路径:
#     powershell.exe -ExecutionPolicy Bypass -File "C:\Users\92893\WorkBuddy\2026-07-30-18-09-13\withdraw-dashboard-cloud\sync\register_dashboard_task.ps1"
#   -ExecutionPolicy Bypass 仅本次生效, 不会修改系统策略。
# 说明: 脚本路径无关, 无论仓库放在哪个目录都能正确定位 bat。

$ErrorActionPreference = "Stop"

# 从脚本自身位置推导仓库根(repo/sync/register_dashboard_task.ps1 -> repo)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo      = Split-Path -Parent $scriptDir
$bat       = Join-Path $repo "sync\同步到云端看板.bat"

if (-not (Test-Path $bat)) {
    Write-Error "找不到同步脚本: $bat"
    exit 1
}

# 任务动作: 用 cmd 跑 bat (bat 内部已 cd 到项目根并调用 python)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ('/c "' + $bat + '"')

# 设置: 允许用电池/不中断, 最长 10 分钟
# 注意: -StartWhenAvailable 与今天已过触发时间组合在某些系统会报 0x80070057, 故移除
$set = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# 工作日触发 (周一到周五)
$days = [System.DayOfWeek]::Monday, [System.DayOfWeek]::Tuesday, [System.DayOfWeek]::Wednesday, [System.DayOfWeek]::Thursday, [System.DayOfWeek]::Friday

Register-ScheduledTask -TaskName "承运提现看板推送-早09:05" -Action $action `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "09:05") `
    -Settings $set -Force | Out-Null

Register-ScheduledTask -TaskName "承运提现看板推送-午15:15" -Action $action `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "15:15") `
    -Settings $set -Force | Out-Null

Write-Host "OK: 已注册两个定时推送任务 (工作日 09:05 / 15:15), 本机全自动推送看板。"
Write-Host "提示: 云端 GitHub Actions 已加防护(抓取失败自动跳过推送, 不再污染数据), 与本地任务可同时运行。"