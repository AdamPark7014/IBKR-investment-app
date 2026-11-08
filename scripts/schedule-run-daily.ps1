#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query the daily run tasks: plan (after the close), execute (after the open)
  and heartbeat-check (dead man's switch).
.NOTES
  EXECUTION__MODE=shadow (default) sends zero orders; execute then does nothing.
  Times are LOCAL to this PC: set them to NYSE close + 45 min and open + 10 min in your time zone.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$PlanTime = '16:45',
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
            $inner = "Set-Location -LiteralPath '$RepoRoot'; $runner $($t.Args)"
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
