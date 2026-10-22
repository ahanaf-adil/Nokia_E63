# Register (or update) a Windows scheduled task that starts E63Tube at boot, before anyone logs in.
# Run once from an elevated PowerShell in this folder. Output goes to cache\server.log.
# Remove with: Unregister-ScheduledTask -TaskName E63Tube -Confirm:$false
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$python = (Get-Command python).Source
New-Item -ItemType Directory -Force (Join-Path $here 'cache') | Out-Null

$action = New-ScheduledTaskAction -Execute 'cmd.exe' -WorkingDirectory $here `
    -Argument "/c `"`"$python`" -u e63tube.py >> cache\server.log 2>&1`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = 'PT30S'   # give the network adapter a moment after boot
# S4U: runs as the current user without a stored password (local files only, which is all it needs).
# Account name from the running identity ($env:USERDOMAIN can be stale after a PC rename).
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName 'E63Tube' -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description 'E63Tube server for the Nokia E63 (http://<this-pc>:8063/)' -Force | Out-Null
Get-ScheduledTask -TaskName 'E63Tube' | Select-Object TaskName, State
