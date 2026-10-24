#Requires -Version 5.1

<#
.SYNOPSIS
    Register/unregister/query/run-once daily Windows Task Scheduler for ibtrader ibc-checklist.

.DESCRIPTION
    Manages a scheduled task to run the ibc-checklist script via Python or ibtrader executable.
    WARNING: PAPER triage only — zero broker orders — NO LIVE trading.
    This script mirrors the structure and style of schedule-reconcile.ps1.

.NOTES
    Author: Adam's Local Coder
    TaskName: ibtrader-ibc-check
    Schedule Time Default: 08:00
#>

[CmdletBinding()]
param(
    [ValidateSet('Register', 'Unregister', 'Status', 'RunOnce')]
    [string]$Action = 'Status',
    
    [string]$Time = '08:00'
)

$RepoRoot = $PSScriptRoot.Parent.FullName
$TaskName = 'ibtrader-ibc-check'
$ScriptCmdPath = Join-Path $RepoRoot "scripts" "ibc-checklist.ps1"

# Resolve the Python executable path (prefer venv, fallback to system)
$PythonExePath = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExePath)) {
    $PythonExePath = "python.exe"
}

# Resolve the ibtrader executable path
$IbtraderCmdPath = Join-Path $RepoRoot ".venv\Scripts\ibtrader"
if (-not (Test-Path $IbtraderCmdPath)) {
    $IbtraderCmdPath = "ibtrader"
}

# Function to determine the actual command to execute
function Get-CommandToRun {
    # Attempt to use Python module first as per script structure preference
    if (Test-Path "$PythonExePath") {
        return & $PythonExePath -m ibtrader.ops.cli ibc-checklist
    }
    else {
        return & $IbtraderCmdPath ibc-checklist
    }
}

if ($Action -eq 'Register') {
    Write-Warning "PAPER triage only — zero broker orders — NO LIVE trading."
    
    # Check if task already exists
    $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($ExistingTask) {
        Write-Host "Task '$TaskName' already exists. Skipping registration." -ForegroundColor Yellow
    }
    else {
        # Prepare the action XML string to avoid encoding issues with special chars in commands
        $ActionXml = @"
<Register>
  <Source>`n`n      `0x1307$([System.Convert]::ToByte($('python.exe -m ibtrader.ops.cli ibc-checklist'), [ConsoleEncoding]::OEM))`n    </Source>
</Register>
"@
        # Replace source with actual command if python path is different, but standard XML action uses 'Command' element usually.
        # Standard approach for PS scripts mimicking shell:
        $ActionElement = "<Command>$(Get-CommandToRun | Out-String)</Command>"
        
        try {
            Register-ScheduledTask -TaskName $TaskName `
                -Action $ActionElement `
                -Trigger (New-ScheduledTaskTrigger -Daily -At $Time) `
                -RunAs LocalSystem `
                -Force
            Write-Host "Task '$TaskName' registered successfully to run at $Time." -ForegroundColor Green
        }
        catch {
            Write-Error "Failed to register task: $_"
        }
    }
}
elseif ($Action -eq 'Unregister') {
    Write-Warning "PAPER triage only — zero broker orders — NO LIVE trading."
    
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Task '$TaskName' unregistered successfully." -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to unregister task: $_"
    }
}
elseif ($Action -eq 'Status') {
    try {
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
        if ($taskInfo) {
            Write-Host "Task '$TaskName' Status: $($taskInfo.Status.ToString())" -ForegroundColor Cyan
            Write-Host "Next Run: $($taskInfo.NextScheduledRunTime)" -ForegroundColor Cyan
            Write-Host "Last Run Time: $($taskInfo.LastRunTime)" -ForegroundColor Cyan
        }
        else {
            Write-Warning "Task '$TaskName' is not found in the scheduler." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Warning "Task '$TaskName' does not exist or error occurred: $_"
    }
}
elseif ($Action -eq 'RunOnce') {
    Write-Warning "PAPER triage only — zero broker orders — NO LIVE trading."
    try {
        $result = Get-CommandToRun
        if ($LASTEXITCODE -eq 0) {
            Write-Host "ibc-checklist completed successfully." -ForegroundColor Green
        }
        else {
            Write-Warning "ibc-checklist exited with code: $($LASTEXITCODE)" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Error "Failed to run ibc-checklist once: $_"
    }
}

# Exit with the last exit code if a command was executed directly (RunOnce), otherwise default 0
if ($Action -eq 'RunOnce') {
    Exit $LASTEXITCODE
}

Exit 0