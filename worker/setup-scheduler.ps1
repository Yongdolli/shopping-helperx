# Registers Shopping Helper worker jobs in Windows Task Scheduler (runs while you are logged on; missed runs start when the PC wakes).
#   collect : every hour at :17 (price check + deal feed + market price check)
#   digest  : 08:00, 12:30, 19:00
#   report  : Monday 09:00
# Remove all:  Get-ScheduledTask -TaskName 'ShoppingHelper-*' | Unregister-ScheduledTask -Confirm:$false
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'run-task.cmd'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

function Register-Job($name, $arg, $triggers) {
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$runner`" $arg" -WorkingDirectory $PSScriptRoot
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Description 'Shopping Helper worker' -Force | Out-Null
    Write-Output "registered $name"
}

$hourly = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddMinutes(17)) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-Job 'ShoppingHelper-Collect' 'collect' $hourly
Register-Job 'ShoppingHelper-Digest' 'digest' @(
    (New-ScheduledTaskTrigger -Daily -At '08:00'),
    (New-ScheduledTaskTrigger -Daily -At '12:30'),
    (New-ScheduledTaskTrigger -Daily -At '19:00'))
Register-Job 'ShoppingHelper-Report' 'report' (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '09:00')
