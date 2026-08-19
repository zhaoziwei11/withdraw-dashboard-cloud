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

function Register-DashboardTask {
    param(
        [string]$TaskName,
        [string]$StartBoundary
    )

    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>承运提现看板自动推送（工作日 $StartBoundary）</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$StartBoundary</StartBoundary>
      <ScheduleByWeek>
        <DaysOfWeek>
          <Monday/><Tuesday/><Wednesday/><Thursday/><Friday/>
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <AllowStartIfOnBatteries>true</AllowStartIfOnBatteries>
    <DontStopIfGoingOnBatteries>true</DontStopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "$bat"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

    $tmp = [System.IO.Path]::GetTempFileName() + ".xml"
    [System.IO.File]::WriteAllText($tmp, $xml, [System.Text.Encoding]::Unicode)
    try {
        schtasks.exe /CREATE /XML "$tmp" /TN "$TaskName" /F | Out-String | Write-Host
        if ($LASTEXITCODE -ne 0) {
            throw "schtasks.exe 返回非零退出码: $LASTEXITCODE"
        }
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

Register-DashboardTask -TaskName "承运提现看板推送-早09:05" -StartBoundary "2026-08-20T09:05:00"
Register-DashboardTask -TaskName "承运提现看板推送-午15:15" -StartBoundary "2026-08-20T15:15:00"

Write-Host "OK: 已注册两个定时推送任务 (工作日 09:05 / 15:15), 本机全自动推送看板。"
Write-Host "提示: 云端 GitHub Actions 已加防护(抓取失败自动跳过推送, 不再污染数据), 与本地任务可同时运行。"