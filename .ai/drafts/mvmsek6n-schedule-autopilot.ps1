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

Write-Host "PAPER TRIAGE ONLY - Zero broker orders, NO LIVE"

$TaskName = 'ibtrader-autopilot'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ($Action -eq "Register") {
    # Build TR string
    $VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    
    if (Test-Path $VenvPy) {
        # Prefer venv, build /TR with Set-Location and single quotes for schtasks
        $Tr = @'
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '$RepoRoot'; & '$VenvPy' -m ibtrader.ops.cli autopilot"
 '@
    } elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
        # Fallback to global command if venv not found
        $Tr = @'
Set-Location; & 'ibtrader' -m ibtrader.ops.cli autopilot
 '@
    } else {
        Write-Error "Neither venv python nor global ibtrader command found. Exit 1."
        exit 1
    }

    # Create task
    schtasks /Create /TN $TaskName /TR $Tr /SC DAILY /ST $Time /F | Out-Null
    
    # Idempotent check using schtasks exit code or query
    if (-not (Get-ScheduledTask -ErrorAction SilentlyContinue -TaskName $TaskName)) {
        Write-Warning "Failed to register task $TaskName."
    } else {
        Write-Host "Registered $TaskName daily at $Time (PAPER TRIAGE ONLY) from $RepoRoot"
    }
} elseif ($Action -eq "Unregister") {
    # Delete task, missing is OK. Do NOT resolve python here.
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    
    if (-not (Get-ScheduledTask -ErrorAction SilentlyContinue -TaskName $TaskName)) {
        Write-Host "Task $TaskName removed or never existed (OK)."
    } else {
        Write-Host "Unregistered $TaskName."
    }
} elseif ($Action -eq "Status") {
    # Query task status. Do NOT resolve python here.
    $QueryResult = schtasks /Query /TN $TaskName /V /FO LIST 2>$null
    
    if (-not $? -or $LASTEXITCODE -ne 0) {
        Write-Host 'Task not registered.'
    } else {
        Write-Host $QueryResult
    }
}