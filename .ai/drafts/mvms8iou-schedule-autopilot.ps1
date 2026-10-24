#Requires -Version 5.1
<#
.SYNOPSIS
  Register/unregister daily paper autopilot (zero broker orders, NO LIVE).
.PARAMETER Action
  Register | Unregister | Status
.PARAMETER Time
  Daily start time (HH:MM), default 16:30
.NOTES
  PAPER TRIAGE ONLY — no broker orders.
  No log files, no config, no --quiet flags.
#>
param(
  [ValidateSet("Register", "Unregister", "Status")]
  [string]$Action = "Status",
  [string]$Time = "16:30"
)

$TaskName = 'ibtrader-autopilot'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'

$Tr = if (Test-Path $VenvPy) {
    "$VenvPy -m ibtrader.ops.cli autopilot"
} elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
    "ibtrader autopilot"
} else {
    Write-Error "Neither venv python nor global ibtrader command found. Exit 1."
    exit 1
}

if ($Action -eq "Register") {
    schtasks /Create /TN $TaskName /TR "$Tr" /SC DAILY /ST $Time /F | Out-Null
    if (-not (Get-ScheduledTask -ErrorAction SilentlyContinue -TaskName $TaskName)) {
        Write-Warning "Failed to register task $TaskName."
    } else {
        Write-Host "Registered $TaskName daily at $Time (PAPER TRIAGE ONLY)."
    }
} elseif ($Action -eq "Unregister") {
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    if (-not (Get-ScheduledTask -ErrorAction SilentlyContinue -TaskName $TaskName)) {
        Write-Host "Task $TaskName removed or never existed (OK)."
    } else {
        Write-Host "Unregistered $TaskName."
    }
} elseif ($Action -eq "Status") {
    schtasks /Query /TN $TaskName /V /FO LIST 2>$null
}