# WARNING: PAPER TRIAGE ONLY — ZERO BROKER ORDERS — NO LIVE TRADING
# This script manages a daily watchdog task that simulates or reports on trading status.
# It does NOT execute real broker orders and is intended for testing/monitoring environments only.

param(
    [ValidateSet('Register','Unregister','Status')]
    [string]$Action = 'Status',
    [string]$Time = '16:30'  # Local HH:mm for daily trigger
)

# Resolve repo root (parent of scripts folder)
$RepoRoot = Join-Path ($PSScriptRoot..'..') | Split-Path -Parent

# Determine Python executable path
$PyPath = "$RepoRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $PyPath)) {
    # Fallback to module if available in PATH
    if (Get-Command ibtrader -ErrorAction SilentlyContinue) {
        $PyPath = "ibtrader"
        $UseModule = $true
    } else {
        Write-Host "[ERROR] Neither .venv\Scripts\python.exe nor 'ibtrader' module found in PATH." -ForegroundColor Red
        exit 1
    }
}

# Construct the command string for the Task Scheduler
# We use PowerShell to set the working directory before running the script
$CommandTemplate = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `\"Set-Location -LiteralPath '{0}'; & '{1}' -m ibtrader.ops.cli autopilot`\""
$ScriptArgs = "-m ibtrader.ops.cli autopilot"
$FullCommand = $CommandTemplate -f $RepoRoot, $PyPath

Write-Host "=== ADAM LOCAL CODER: IBTRADER AUTOPILOT MANAGER ==="
Write-Host "Action: $($Action.ToUpper())"
Write-Host "Time Trigger: $($Time)"
Write-Host "Repo Root: $($RepoRoot)"
Write-Host "Command: $FullCommand"
Write-Host ""

if ($Action -eq 'Register') {
    Write-Host "[REGISTER] Creating daily task 'ibtrader-autopilot'..." -ForegroundColor Cyan
    
    # Ensure task name is sanitized (remove special chars if any)
    $TaskName = "ibtrader-autopilot"
    
    # Create the task, overwriting existing one with /F
    $ErrorActionPreference = 'Stop'
    
    # Using schtasks to create a persistent Windows Task Scheduler job
    $Cmd = "/Create /TN `"$TaskName`" /TR `\"$FullCommand`" /SC DAILY /ST 16:30 /RL LIMITED /F"
    
    try {
        schtasks.exe $Cmd
        Write-Host "[SUCCESS] Task '$TaskName' registered successfully for daily execution at $($Time)." -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] Failed to register task: $_" -ForegroundColor Red
        exit 1
    }
} elseif ($Action -eq 'Unregister') {
    Write-Host "[UNREGISTER] Deleting task 'ibtrader-autopilot'..." -ForegroundColor Cyan
    
    $TaskName = "ibtrader-autopilot"
    
    try {
        schtasks.exe /Delete /TN "$TaskName" /F
        Write-Host "[SUCCESS] Task '$TaskName' unregistered (or already missing)." -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Failed to delete task: $_" -ForegroundColor Yellow
    }
} elseif ($Action -eq 'Status') {
    Write-Host "[STATUS] Checking status of task 'ibtrader-autopilot'..." -ForegroundColor Cyan
    
    try {
        $TaskInfo = schtasks.exe /Query /TN "ibtrader-autopilot" /V /FO LIST 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host $TaskInfo
            Write-Host ""
            Write-Host "[INFO] Task exists and is configured." -ForegroundColor Green
        } else {
            Write-Host "Task 'ibtrader-autopilot' not found in Windows Task Scheduler." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to query task: $_" -ForegroundColor Red
    }
}