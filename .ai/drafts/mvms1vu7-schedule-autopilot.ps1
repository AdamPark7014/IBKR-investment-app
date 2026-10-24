Param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action,
    [string]$Time = '16:30'
)

# Configuration
$TaskName = 'ibtrader-autopilot'
$WorkingDirectory = Split-Path -Parent $PSScriptRoot
if ($PWD.Parent.FullName -ne $WorkingDirectory) { $WorkingDirectory = Split-Path -Parent $PWD.FullName }
$LogPath = Join-Path $WorkingDirectory 'logs\'
$logFile = Join-Path $LogPath "schedule-autopilot_${Get-Date -Format 'yyyyMMdd_HHmmss'}"

function Write-Log {
    param([string]$Message)
    try {
        if (-not (Test-Path $logFile)) { New-Item -ItemType Directory -Path $LogPath -Force | Out-Null }
        [PSCustomObject]@{ Time = Get-Date; Message = $Message } | ConvertTo-Json >> $logFile
    } catch { Write-Warning "Failed to write log: $_" }
}

function Register-Scheduler {
    $VenvPython = Join-Path (Join-Path $WorkingDirectory 'venv') 'Scripts\python.exe'
    $ScriptPath = Join-Path $WorkingDirectory 'scripts\ibtrader\ops\cli.py'
    
    $PythonCommand = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
    $CommandLine = "$PythonCommand -m ibtrader.ops.cli autopilot --quiet --config $(Split-Path $WorkingDirectory)"
    $ScheduleString = "@16:30:00 ;daily ? * *"
    
    try {
        $TaskAlreadyExists = schtasks /Query /TN $TaskName /V /FO LIST 2>$null | Select-String -Pattern $TaskName | Measure-Object
        if ($TaskAlreadyExists.Count -gt 0) { Remove-ScheduledTaskTask -TN $TaskName }
        
        schtasks /Create /TN $TaskName /TR "$CommandLine" /RU SYSTEM /SC DAILY /ST $Time /F
        Write-Host "[SUCCESS] Task registered: $TaskName" -ForegroundColor Green
        Write-Log "Registered task $TaskName at $($Time)".trim()
    } catch {
        Write-Host "Failed to register task: $_" -ForegroundColor Red
        throw
    }
}

function Unregister-Scheduler {
    try {
        schtasks /Delete /TN $TaskName /F
        Write-Host "[SUCCESS] Task unregistered: $TaskName" -ForegroundColor Green
        Write-Log "Unregistered task $TaskName".trim()
    } catch {
        if ($_.Exception.Message -notlike "*Error: Task.*not found*") {
            Write-Host "Failed to unregister task: $_" -ForegroundColor Red
            throw
        } else {
            Write-Host "[INFO] Task $TaskName not found. Nothing to remove." -ForegroundColor Cyan
        }
    }
}

function Get-SchedulerStatus {
    try {
        $Result = schtasks /Query /TN $TaskName /V /FO LIST 2>$null
        if ($?) { Write-Host "Task Status: $($Result.Substring(0, [Math]::Min(500, $Result.Length)))" -ForegroundColor Yellow } else { Write-Host "Task not found or error querying." -ForegroundColor Red }
    } catch {
        Write-Host "Error checking status: $_" -ForegroundColor Red
    }
}

# Main Execution
Write-Host "=== IBTrader Autopilot Scheduler ($(Get-Date)) ===" 
Write-Host "Action: $Action | Time: $Time | Dir: $($WorkingDirectory.TrimEnd('\'))"
Write-Host "Note: PAPER ONLY. NO LIVE ORDERS." -ForegroundColor Cyan

switch ($Action) {
    'Register' { Register-Scheduler }
    'Unregister' { Unregister-Scheduler }
    'Status' { Get-SchedulerStatus }
}