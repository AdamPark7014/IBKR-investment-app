#Requires -Version 5.1
<#
.SYNOPSIS
  Register/unregister daily paper autopilot (zero broker orders).
.PARAMETER Action
  Register | Unregister | Status
#>
param(
  [ValidateSet("Register", "Unregister", "Status")]
  [string]$Action = "Status",
  [string]$Time = "16:30",
  [string]$TaskName = "ibtrader-autopilot"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
  throw "Missing venv python: $VenvPy"
}

# Paper triage only — no LIVE, no broker orders.
$Args = "-m ibtrader.ops.cli autopilot"

switch ($Action) {
  "Unregister" {
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    Write-Host "Removed task $TaskName (if it existed)."
  }
  "Register" {
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    $tr = "`"$VenvPy`" $Args"
    schtasks /Create /TN $TaskName /SC DAILY /ST $Time /TR $tr /RL LIMITED /F | Out-Null
    # Working directory is not set by schtasks /TR alone; wrap via cmd /c cd
    $tr2 = "cmd /c `"cd /d `"$Repo`" && `"$VenvPy`" $Args`""
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    schtasks /Create /TN $TaskName /SC DAILY /ST $Time /TR $tr2 /RL LIMITED /F
    Write-Host "Registered $TaskName daily at $Time (paper autopilot, 0 orders)."
  }
  "Status" {
    schtasks /Query /TN $TaskName /V /FO LIST
  }
}
