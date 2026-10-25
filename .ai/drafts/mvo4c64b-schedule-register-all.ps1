#Requires -Version 5.1

Synopsis: Register / unregister / query ALL three ibtrader Task Scheduler jobs (autopilot, paper-reconcile, ibc-check) in one call.
Notes: PAPER triage only — zero broker orders — NO LIVE trading.

$ErrorActionPreference = 'Stop'
$Banner = 'PAPER triage only — zero broker orders — NO LIVE.'
Write-Host $Banner -ForegroundColor Cyan

$ScriptsDir = $PSScriptRoot

function Invoke-ScheduleAll {
    [CmdletBinding()]
    param (
        [ValidateSet('Register','Unregister','Status')][string]$Action = 'Status',
        [string]$AutopilotTime = '16:30',
        [string]$ReconcileTime = '16:35',
        [string]$IbcTime = '08:00'
    )

    $ExitCode = 0

    if ($Action -ne 'Status') {
        & (Join-Path $ScriptsDir 'schedule-autopilot.ps1') `
            -Action $Action `
            -Time $AutopilotTime | Out-Null
        
        if ($LASTEXITCODE -ne 0) { $ExitCode = $LASTEXITCODE }

        & (Join-Path $ScriptsDir 'schedule-reconcile.ps1') `
            -Action $Action `
            -Time $ReconcileTime | Out-Null
        
        if ($LASTEXITCODE -ne 0) { 
            if ($LASTEXITCODE -ne $ExitCode) { $ExitCode = $LASTEXITCODE } 
        }

        & (Join-Path $ScriptsDir 'schedule-ibc-check.ps1') `
            -Action $Action `
            -Time $IbcTime | Out-Null
        
        if ($LASTEXITCODE -ne 0) { 
            if ($LASTEXITCODE -ne $ExitCode) { $ExitCode = $LASTEXITCODE } 
        }
    }
    
    else { # Status mode
        & (Join-Path $ScriptsDir 'schedule-autopilot.ps1') -Action $Action | Out-Null
        & (Join-Path $ScriptsDir 'schedule-reconcile.ps1') -Action $Action | Out-Null
        & (Join-Path $ScriptsDir 'schedule-ibc-check.ps1') -Action $Action | Out-Null
    }

    return $ExitCode
}

Invoke-ScheduleAll -Action $Action -AutopilotTime $AutopilotTime -ReconcileTime $ReconcileTime -IbcTime $IbcTime
exit $LASTEXITCODE