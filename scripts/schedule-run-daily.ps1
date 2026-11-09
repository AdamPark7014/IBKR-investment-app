#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query the daily run tasks: plan (after the close), execute (after the open)
  and heartbeat-check (dead man's switch).
.NOTES
  EXECUTION__MODE=shadow (default) sends zero orders; execute then does nothing.
  Times are LOCAL to this PC. Plan = 19:00 New York (Tiingo publishes end-of-day prices around
  17:30-18:00 ET and corrects them later; earlier runs see yesterday's bar and block). Execute =
  10:05 New York (open + 35 min: ETF spreads are widest at the open). Convert both to your time zone.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$PlanTime = '19:00',
    [string]$ExecuteTime = '10:05',
    [string]$HeartbeatTime = '12:00'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Tasks = @(
    @{ Name = 'ibtrader-run-daily-plan'; Args = 'run-daily --phase plan'; Time = $PlanTime; Days = 'MON,TUE,WED,THU,FRI' },
    @{ Name = 'ibtrader-run-daily-execute'; Args = 'run-daily --phase execute'; Time = $ExecuteTime; Days = 'MON,TUE,WED,THU,FRI' },
    @{ Name = 'ibtrader-heartbeat-check'; Args = 'heartbeat-check'; Time = $HeartbeatTime; Days = 'TUE,WED,THU,FRI,SAT' }
)

foreach ($t in $Tasks) {
    switch ($Action) {
        'Register' {
            # run-task.ps1 enters the repo, loads the puerta token (Claude copilot/triage) from outside the
            # repo and appends the output to data\logs\<task>.log: a scheduled task has no console.
            $Runner = Join-Path $RepoRoot 'scripts\run-task.ps1'
            $Tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Runner`" -Name $($t.Name) -Command `"$($t.Args)`""
            if ($Tr.Length -gt 261) { Write-Error "La orden de la tarea pasa de 261 caracteres (límite de schtasks): mueve el repo a una ruta más corta."; exit 1 }
            schtasks /Create /TN $t.Name /TR $Tr /SC WEEKLY /D $t.Days /ST $t.Time /F
            if ($LASTEXITCODE -ne 0) { Write-Error "schtasks /Create $($t.Name) failed ($LASTEXITCODE)."; exit $LASTEXITCODE }
            # schtasks /Create cannot set these. A laptop on battery or asleep must not lose the daily run;
            # a late start is safe because run-daily rejects stale plans and orders outside market hours.
            $Task = Get-ScheduledTask -TaskName $t.Name
            $Task.Settings.DisallowStartIfOnBatteries = $false
            $Task.Settings.StopIfGoingOnBatteries = $false
            $Task.Settings.WakeToRun = $true
            $Task.Settings.StartWhenAvailable = $true
            Set-ScheduledTask -InputObject $Task | Out-Null
            Write-Host "Registrada '$($t.Name)' $($t.Days) a las $($t.Time)."
        }
        'Unregister' {
            schtasks /Delete /TN $t.Name /F 2>$null
            if ($LASTEXITCODE -ne 0) { Write-Host "Tarea '$($t.Name)' no encontrada (OK)." } else { Write-Host "Eliminada '$($t.Name)'." }
        }
        'Status' {
            schtasks /Query /TN $t.Name /FO LIST 2>$null
            if ($LASTEXITCODE -ne 0) { Write-Host "Tarea '$($t.Name)' no registrada." }
        }
    }
}
exit 0
