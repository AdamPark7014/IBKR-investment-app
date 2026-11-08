#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query the daily run tasks: plan (after the close), execute (after the open)
  and heartbeat-check (dead man's switch).
.NOTES
  EXECUTION__MODE=shadow (default) sends zero orders; execute then does nothing.
  Times are LOCAL to this PC. Plan = 19:00 New York (Tiingo publishes end-of-day prices around
  17:30-18:00 ET and corrects them later; earlier runs see yesterday's bar and block). Execute =
  09:40 New York (open + 10 min). Convert both to your time zone.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$PlanTime = '19:00',
    [string]$ExecuteTime = '09:40',
    [string]$HeartbeatTime = '12:00'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Tasks = @(
    @{ Name = 'ibtrader-run-daily-plan'; Args = 'run-daily --phase plan'; Time = $PlanTime; Days = 'MON,TUE,WED,THU,FRI' },
    @{ Name = 'ibtrader-run-daily-execute'; Args = 'run-daily --phase execute'; Time = $ExecuteTime; Days = 'MON,TUE,WED,THU,FRI' },
    @{ Name = 'ibtrader-heartbeat-check'; Args = 'heartbeat-check'; Time = $HeartbeatTime; Days = 'TUE,WED,THU,FRI,SAT' }
)

function Get-Runner {
    $VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $VenvPy) { return "& '$VenvPy' -m ibtrader.ops.cli" }
    if (Get-Command ibtrader -ErrorAction SilentlyContinue) { return '& ibtrader' }
    Write-Error "Need repo .venv\Scripts\python.exe or ibtrader on PATH. Repo=$RepoRoot"
    exit 1
}

foreach ($t in $Tasks) {
    switch ($Action) {
        'Register' {
            $runner = Get-Runner
            # Output (JSON summary + logs) is appended to data\logs\<task>.log: a scheduled task has no console.
            $log = "data\logs\$($t.Name).log"
            $inner = "Set-Location -LiteralPath '$RepoRoot'; New-Item -ItemType Directory -Force data\logs | Out-Null; $runner $($t.Args) *>> $log; exit `$LASTEXITCODE"
            $Tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"$inner`""
            schtasks /Create /TN $t.Name /TR $Tr /SC WEEKLY /D $t.Days /ST $t.Time /F
            if ($LASTEXITCODE -ne 0) { Write-Error "schtasks /Create $($t.Name) failed ($LASTEXITCODE)."; exit $LASTEXITCODE }
            Write-Host "Registered '$($t.Name)' $($t.Days) at $($t.Time)."
        }
        'Unregister' {
            schtasks /Delete /TN $t.Name /F 2>$null
            if ($LASTEXITCODE -ne 0) { Write-Host "Task '$($t.Name)' not found (OK)." } else { Write-Host "Unregistered '$($t.Name)'." }
        }
        'Status' {
            schtasks /Query /TN $t.Name /FO LIST 2>$null
            if ($LASTEXITCODE -ne 0) { Write-Host "Task '$($t.Name)' not registered." }
        }
    }
}
exit 0
