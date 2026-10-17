# Passermark Watcher (drop folders) as a scheduled task at system start, with its own user without admin rights.
#
#   powershell -ExecutionPolicy Bypass -File watch-task.ps1 -User passermark
#   powershell -ExecutionPolicy Bypass -File watch-task.ps1 -Remove
#
# Before: create the local user (e.g. "net user passermark * /add"), give it write access to the drop folders,
# install the printers for this user and check the settings: passermark-cli serve --check
param(
    [string]$User = "passermark",
    [string]$Config = (Join-Path $env:ProgramData "Passermark\watch.json"),
    [string]$LogDir = (Join-Path $env:ProgramData "Passermark Watcher"),
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$Name = "Passermark Watcher"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    Write-Host "Removed: $Name"
    exit 0
}
$exe = Join-Path $env:ProgramFiles "Passermark\passermark-cli.exe"
if (-not (Test-Path $exe)) { throw "Not found: $exe" }
if (-not (Test-Path $Config)) { throw "Not found: $Config" }
$cred = Get-Credential -UserName $User -Message "Password of the watcher user"
# log folder the watcher user may write to (the Passermark folder in ProgramData is read-only for users)
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
& icacls.exe $LogDir /grant "${User}:(OI)(CI)M" | Out-Null
$log = Join-Path $LogDir "watch.log"
$action = New-ScheduledTaskAction -Execute $exe -Argument "serve --config `"$Config`" --log `"$log`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings `
    -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName $Name
Write-Host "Registered and started: $Name (user $User, settings $Config, log $log)"
