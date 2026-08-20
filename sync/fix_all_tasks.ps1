# 重新注册承运提现全部定时任务
# 用法: 右键"开始" -> Windows PowerShell (管理员), 运行 fix_all_tasks.bat
$ErrorActionPreference = "Stop"

$repoPush  = "C:\Users\92893\WorkBuddy\2026-07-30-18-09-13\withdraw-dashboard-cloud"
$repoFetch = "C:\Users\92893\WorkBuddy\automation-2026-07-22-13-54-50\withdraw-report"
$py        = "C:\Users\92893\AppData\Local\Programs\Python\Python312\python.exe"

Write-Host "============================================"
Write-Host "  重新注册承运提现定时任务"
Write-Host "============================================"
Write-Host ""
Write-Host "将删除并重建以下 4 个任务:"
Write-Host "  1) WithdrawDailyReport-09   (工作日 09:00 抓取待提现)"
Write-Host "  2) WithdrawDailyReport-15   (工作日 15:00 抓取失败原因+需求二)"
Write-Host "  3) 承运提现看板推送-早0905  (工作日 09:05 推送到 GitHub 看板)"
Write-Host "  4) 承运提现看板推送-午1515 (工作日 15:15 推送到 GitHub 看板)"
Write-Host ""
Write-Host "任务会设置为"无论用户是否登录都运行"，需要输入 Windows 登录密码。"
Write-Host ""

# 删除旧任务(不存在时忽略错误)
@("WithdrawDailyReport-09", "WithdrawDailyReport-15",
  "承运提现看板推送-早0905", "承运提现看板推送-午1515") | ForEach-Object {
    schtasks.exe /DELETE /TN "$_" /F 2>$null | Out-Null
}

# 提示输入密码(不显示)
$secure = Read-Host "请输入 Windows 登录密码(输入时不显示)" -AsSecureString
$cred   = New-Object System.Management.Automation.PSCredential($env:USERNAME, $secure)
$passwd = $cred.GetNetworkCredential().Password

# 创建抓取任务: 直接用 cmd 设置 PYTHONIOENCODING 后调用 Python
$tr09 = 'cmd.exe /c "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && ' + $py + ' ' + $repoFetch + '\withdraw_report.py --pending"'
$tr15 = 'cmd.exe /c "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && ' + $py + ' ' + $repoFetch + '\withdraw_report.py --fail --demand2"'

schtasks.exe /CREATE /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:00  /TN "WithdrawDailyReport-09" /TR "$tr09" /RU $env:USERNAME /RP $passwd /RL HIGHEST /F | Out-String | Write-Host
if ($LASTEXITCODE -ne 0) { throw "创建 WithdrawDailyReport-09 失败" }

schtasks.exe /CREATE /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:00 /TN "WithdrawDailyReport-15" /TR "$tr15" /RU $env:USERNAME /RP $passwd /RL HIGHEST /F | Out-String | Write-Host
if ($LASTEXITCODE -ne 0) { throw "创建 WithdrawDailyReport-15 失败" }

# 创建推送任务: 调用现有 bat
$trPush = 'cmd.exe /c "' + $repoPush + '\sync\同步到云端看板.bat"'
schtasks.exe /CREATE /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:05  /TN "承运提现看板推送-早0905"  /TR "$trPush" /RU $env:USERNAME /RP $passwd /RL HIGHEST /F | Out-String | Write-Host
if ($LASTEXITCODE -ne 0) { throw "创建 承运提现看板推送-早0905 失败" }

schtasks.exe /CREATE /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:15 /TN "承运提现看板推送-午1515" /TR "$trPush" /RU $env:USERNAME /RP $passwd /RL HIGHEST /F | Out-String | Write-Host
if ($LASTEXITCODE -ne 0) { throw "创建 承运提现看板推送-午1515 失败" }

Write-Host ""
Write-Host "[OK] 4 个定时任务已重新注册。"
Write-Host "     下次运行: 明天 09:00 / 09:05 / 15:00 / 15:15"
