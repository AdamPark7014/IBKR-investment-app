#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query ALL ibtrader Task Scheduler jobs in one call:
  run-daily plan + execute + heartbeat-check, and the IBC/Gateway check.
.NOTES
  EXECUTION__MODE=shadow (default) sends zero broker orders.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$PlanTime = '16:45',
    [string]$ExecuteTime = '09:40',
    [string]$HeartbeatTime = '12:00',
    [string]$IbcTime = '08:00'
)

$ErrorActionPreference = 'Stop'
$ScriptsDir = $PSScriptRoot
$exitCode = 0

& (Join-Path $ScriptsDir 'schedule-run-daily.ps1') -Action $Action -PlanTime $PlanTime -ExecuteTime $ExecuteTime -HeartbeatTime $HeartbeatTime
if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }

& (Join-Path $ScriptsDir 'schedule-ibc-check.ps1') -Action $Action -Time $IbcTime
if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }

# Old tasks from the phase-3 triage (autopilot / paper-reconcile were removed on 2026-11-08).
if ($Action -eq 'Register' -or $Action -eq 'Unregister') {
    foreach ($old in @('ibtrader-autopilot', 'ibtrader-paper-reconcile')) { schtasks /Delete /TN $old /F 2>$null | Out-Null }
}

exit $exitCode
