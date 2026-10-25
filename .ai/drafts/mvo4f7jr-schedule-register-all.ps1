#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query ALL three ibtrader Task Scheduler jobs
  (autopilot, paper-reconcile, ibc-check) in one call.
.NOTES
  PAPER triage only — zero broker orders — NO LIVE trading.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$AutopilotTime = '16:30',
    [string]$ReconcileTime = '16:35',
    [string]$IbcTime = '08:00'
)

$ErrorActionPreference = 'Stop'
$ScriptsDir = $PSScriptRoot

Write-Host 'PAPER triage only — zero broker orders — NO LIVE.'

$exitCode = 0

& (Join-Path $ScriptsDir 'schedule-autopilot.ps1') -Action $Action -Time $AutopilotTime
if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }

& (Join-Path $ScriptsDir 'schedule-reconcile.ps1') -Action $Action -Time $ReconcileTime
if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }

& (Join-Path $ScriptsDir 'schedule-ibc-check.ps1') -Action $Action -Time $IbcTime
if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }

exit $exitCode