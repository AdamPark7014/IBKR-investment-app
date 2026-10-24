#Requires -Version 5.1

<#
.SYNOPSIS
    Register/unregister/query/run-once daily Windows Task Scheduler job for ibtrader ibc-checklist

.DESCRIPTION
    Manages the Windows Task Scheduler task 'ibtrader-ibc-check' to execute a daily PAPER triage check using the ibtrader tool.
    This script is strictly for paper trading and triage purposes only. It does not place live broker orders.

.PARAMETER Action
    Specifies the action to perform.
    Valid values: Register, Unregister, Status, RunOnce.
    Default value: Status

.PARAMETER Time
    The time of day (HH:MM format) for scheduled runs.
    Default value: '08:00'

.NOTES
    PAPER triage only — zero broker orders — NO LIVE trading.
#>

param(
    [ValidateSet('Register', 'Unregister', 'Status', 'RunOnce')]
    [string]$Action = 'Status',

    [string]$Time = '08:00'
)

$TaskName = 'ibtrader-ibc-check'
$ScriptFolder = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptFolder

# PAPER triage warning
Write-Host "=== PAPER TRIAGE WARNING ===" -ForegroundColor Yellow
Write-Host "This script performs zero broker orders and NO LIVE trading." -ForegroundColor Cyan
Write-Host "It is strictly for triage purposes." -ForegroundColor Cyan
Write-Host "============================" -ForegroundColor Gray
Start-Sleep -Milliseconds 500

function Get-PythonPath {
    # Prefer virtual environment python first, then PATH fallback
    $venvPython = Join-Path "$RepoRoot\.venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    
    # Check standard Python location
    $stdPython = "${env:ProgramFiles}\Python\Python3*\python.exe"
    if (Test-Path $stdPython) {
        return $stdPython
    }
    
    # Fallback to python on PATH
    try {
        $cmd = "python --version 2>&1"
        $output = Invoke-CommandExpression "$($env:COMSPEC).exe", "-c", $cmd -ErrorAction SilentlyContinue
        if ($LASTEXITCODE -eq 0) {
            return "python"
        }
    } catch {}

    # Check for py launcher
    try {
        $output = Invoke-CommandExpression "$($env:COMSPEC).exe", "-c", "`$py = & '$(python)' --version"; Write-Output `"$(``$py)"; Exit 0" -ErrorAction SilentlyContinue
        if ($LASTEXITCODE -eq 0) { return "py" }
    } catch {}

    # Check for python3
    $pathPython3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($pathPython3) { return $pathPython3.Source }

    throw "Python executable not found. Please ensure Python is installed and available in PATH or within .venv"
}

function Invoke-IbcCheck {
    $python = Get-PythonPath
    try {
        # Run the command directly, capturing exit code
        & $python -m ibtrader.ops.cli ibc-checklist 2>&1 | Write-Host
        $exitCode = $LASTEXITCODE
    } catch {
        $errorMessage = $_.Exception.Message
        throw "Failed to run ibc-checklist: $errorMessage"
    }
    return $exitCode
}

# Main Execution Logic based on Action
if ($Action -eq 'Register') {
    Write-Host "Registering task '$TaskName' at time '$Time'..." -ForegroundColor Green
    try {
        $python = Get-PythonPath
        
        # schtasks syntax: Create, /TN TaskName /TR Command /RU System /RL Limit64K /SC DAILY /ST StartTime /F (Force)
        # Note: We use /RU SYSTEM or Interactive depending on user policy, but typically SYSTEM for scheduled tasks is preferred for backend.
        # However, standard user task usually runs under current user. Let's assume interactive or specific service account context if needed.
        # For simplicity and standard deployment, we often run as the logged-in user or SYSTEM. 
        # We will use SYSTEM to ensure it runs regardless of UI state, unless restricted by UAC policies.
        # A safer default for scripts is often just running under current user with /F flag.
        
        $cmd = "-m ibtrader.ops.cli ibc-checklist"
        
        # Construct the command string with proper escaping
        $fullCommand = "& ''$python'' $cmd"
        
        schtasks /Create `/
            /TN $TaskName `/
            /TR "`"$fullCommand`"" `/
            /SC DAILY `/
            /ST $Time `/
            /RL High /
            /RU SYSTEM 2>&1 | Write-Host
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Task registered successfully." -ForegroundColor Green
        } else {
            throw "Failed to create task"
        }
    } catch {
        throw $_.Exception.Message
    }

} elseif ($Action -eq 'Unregister') {
    Write-Host "Unregistering task '$TaskName'..." -ForegroundColor Red
    try {
        schtasks /Delete `/
            /TN $TaskName `/
            /F 2>&1 | Write-Host
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Task deleted successfully." -ForegroundColor Green
        } else {
            throw "Failed to delete task"
        }
    } catch {
        throw $_.Exception.Message
    }

} elseif ($Action -eq 'Status') {
    Write-Host "Checking status of task '$TaskName'..." -ForegroundColor Cyan
    try {
        $output = schtasks /Query `/
            /TN $TaskName `/
            /V 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host $output
        } else {
            Write-Host "Task not found or inactive." -ForegroundColor Gray
        }
    } catch {
        throw $_.Exception.Message
    }

} elseif ($Action -eq 'RunOnce') {
    Write-Host "Running ibc-checklist immediately (not scheduled)..." -ForegroundColor Green
    try {
        $python = Get-PythonPath
        
        # Execute command directly
        & $python -m ibtrader.ops.cli ibc-checklist
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Command completed successfully." -ForegroundColor Green
            exit 0
        } else {
            Write-Host "Command failed with exit code: $($LASTEXITCODE)" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    } catch {
        Write-Error "Error running command: $_"
        exit 1
    }
} else {
    throw "Invalid Action specified."
}

exit 0