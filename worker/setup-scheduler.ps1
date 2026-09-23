# If the PC sleeps mid-run, the frozen run is does not block the next one (Parallel; storage writes are idempotent) and is killed by the time limit.
# Registers Shopping Helper worker jobs in Windows Task Scheduler (runs while you are logged on; missed runs start when the PC wakes).
#   collect : every hour at :47 (GitHub Actions runs at :17 -> no simultaneous runs)
#   digest  : 08:00, 12:30, 19:00   } registered DISABLED unless -WithDigest (GitHub Actions sends them;
#   report  : Monday 09:00          }  enabling both would send duplicates)
# Remove all:  Get-ScheduledTask -TaskName 'ShoppingHelper-*' | Unregister-ScheduledTask -Confirm:$false
param([switch]$WithDigest)
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'run-task.cmd'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances Parallel

function Register-Job($name, $arg, $triggers, [bool]$enabled = $true) {
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$runner`" $arg" -WorkingDirectory $PSScriptRoot
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Description 'Shopping Helper worker' -Force | Out-Null
    if (-not $enabled) { Disable-ScheduledTask -TaskName $name | Out-Null }
    Write-Output "registered $name (enabled=$enabled)"
}

$hourly = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddMinutes(47)) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-Job 'ShoppingHelper-Collect' 'collect' $hourly
Register-Job 'ShoppingHelper-Digest' 'digest' @(
    (New-ScheduledTaskTrigger -Daily -At '08:00'),
    (New-ScheduledTaskTrigger -Daily -At '12:30'),
    (New-ScheduledTaskTrigger -Daily -At '19:00')) $WithDigest.IsPresent
Register-Job 'ShoppingHelper-Report' 'report' (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '09:00') $WithDigest.IsPresent
