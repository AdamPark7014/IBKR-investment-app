#requires -Version 5.1
$ErrorActionPreference = 'Stop'
$currentPath = $PSScriptRoot
$parentDir = Split-Path -Parent $currentPath
$RepoRoot = Join-Path $parentDir '..\repo'

<#
.SYNOPSIS
    Creates a Windows Task Scheduler job for daily ibtrader paper-reconcile.
.DESCRIPTION
    Runs the paper-reconcile script at 16:35 to synchronize IBKR accounts with the trading platform.
    This is PAPER triage only — zero broker orders — NO LIVE trading.
.PARAMETER Action
    Register|Unregister|Status - default Status
.PARAMETER Time
    Scheduled time - default '16:35'
.EXAMPLE
    .\schedule-reconcile.ps1 -Action Register
.EXAMPLE
    .\schedule-reconcile.ps1 -Action Unregister
.EXAMPLE
    .\schedule-reconcile.ps1 -Status
#>

param(
    [string]$Action = 'Status',
    [string]$Time = '16:35'
)

$TaskName = 'ibtrader-paper-reconcile'
$schedulerPath = "schtasks /Query /TN $TaskName"
$pythonCmd = "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe -m ibtrader.ops.cli paper-reconcile"
$repoPath = Join-Path $RepoRoot 'ibtrader'\ops\cli.py

function Write-Header {
    <#
    .SYNOPSIS
        Prints the job header banner.
    .DESCRIPTION
        Displays the PAPER triage warning and job details for schedule-reconcile.ps1.
    #>
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "     IBTRADER PAPER-RECONCILE SCHEDULER" -ForegroundColor Yellow
    Write-Host "     ---------------------------------" -ForegroundColor Gray
    Write-Host "     DATE: $(Get-Date -Format 'yyyy-MM-dd')" -ForegroundColor White
    Write-Host "     TIME: $Time" -ForegroundColor Green
    Write-Host "     ACTION: $Action" -ForegroundColor Cyan
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "" -NoNewline

    <#
    .SYNOPSIS
        Displays the PAPER triage warning.
    #>
    function Warn-Paper {
        Write-Host "WARNING: PAPER TRIAGE ONLY" -ForegroundColor DarkRed
        Write-Host "         ZERO BROKER ORDERS" -ForegroundColor DarkRed
        Write-Host "         NO LIVE TRADING" -ForegroundColor DarkRed
    }

    if ($Action -eq 'Status') {
        $exists = schtasks /Query /TN $TaskName 2>$null | Select-Object -ExpandProperty ExitCode -ErrorAction SilentlyContinue
        if (-not $exists) {
            Warn-Paper
            Write-Host "Job '$TaskName' does NOT exist. Registering..." -ForegroundColor Yellow
        } else {
            Warn-Paper
            Write-Host "Job '$TaskName' already exists." -ForegroundColor Green
        }
    } elseif ($Action -eq 'Register') {
        Warn-Paper
        Write-Host "Creating new scheduled task '$TaskName' for daily paper-reconcile..." -ForegroundColor Yellow
    }
}

function Get-ScheduledCommand {
    <#
    .SYNOPSIS
        Constructs the command string for the scheduled task.
    #>
    $cmdPath = Join-Path $currentPath '..\ibtrader\.venv\Scripts\python.exe'
    if (Test-Path $cmdPath) {
        return "`"$cmdPath`" -m ibtrader.ops.cli paper-reconcile"
    } else {
        Write-Warning "Specific venv python not found at '$cmdPath'. Falling back to PATH check."
        $py = Get-Command python -ErrorAction SilentlyContinue
        if ($py) {
            return "$($py.Source) -m ibtrader.ops.cli paper-reconcile"
        } else {
            Write-Error "Cannot find Python executable on PATH or in expected venv."
            return $null
        }
    }
}

function Set-ScheduledTask {
    <#
    .SYNOPSIS
        Registers the task with schtasks.
    #>
    if ($Action -eq 'Unregister') {
        Write-Host "Removing task '$TaskName'..." -ForegroundColor Yellow
        $null = schtasks /Delete /TN $TaskName /F 2>$null
        if ($LASTEXITCODE -ne 0) {
            Throw "Failed to delete task."
        }
    } elseif ($Action -eq 'Register') {
        Write-Host "Registering task '$TaskName'..." -ForegroundColor Yellow
        $cmd = Get-ScheduledCommand
        if (-not $cmd) { return }

        $null = schtasks /Create /TN $TaskName /RU "$cmd" /SC DAILY /ST $Time /F 2>$null
        if ($LASTEXITCODE -ne 0) {
            Throw "Failed to create task."
        }
    } elseif ($Action -eq 'Status') {
        $null = schtasks /Query /TN $TaskName
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Task status failed to retrieve."
        }
    }
}

function Main {
    <#
    .SYNOPSIS
        Main execution logic.
    #>
    try {
        Write-Header
        Set-ScheduledTask
    } catch {
        Write-Host "Error occurred: $_" -ForegroundColor Red
        exit 1
    }
}

Main