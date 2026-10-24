# schedule-autopilot.ps1
# Registers a daily Windows Task Scheduler job for ibtrader autopilot.
# PAPER triage only — zero broker orders — NO LIVE trading.

param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$Time = '16:30'
)

$TaskName = 'ibtrader-autopilot'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'

function Invoke-Autopilot {
    $CmdLine = ''
    if (Test-Path $VenvPy) {
        $CmdLine = "`"$VenvPy`" -m ibtrader.ops.cli autopilot"
    } elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
        $CmdLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `\"Set-Location -LiteralPath '$RepoRoot'; & 'ibtrader' autopilot`\""
    } else {
        Write-Error "Could not find Python environment or ibtrader command."
        exit 1
    }
    return $CmdLine
}

switch ($Action) {
    'Register' {
        Write-Host "PAPER triage only - zero broker orders" -ForegroundColor Cyan
        $Tr = Invoke-Autopilot
        if (-not [string]::IsNullOrWhiteSpace($Tr)) {
            try {
                schtasks /Create /TN $TaskName /TR "`"$Tr`"" /SC DAILY /ST $Time /F | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Success: Task '$TaskName' registered for $($Time)" -ForegroundColor Green
                } else {
                    exit $LASTEXITCODE
                }
            } catch {
                Write-Error $_.Exception.Message
                exit 1
            }
        }
    }
    'Unregister' {
        try {
            schtasks /Delete /TN $TaskName /F | Out-Null
            # Missing task is treated as OK per requirements
        } catch {
            if ($_.Exception.Message -notlike "*Error: Task.*not found*") {
                Write-Error $_.Exception.Message
                exit 1
            }
        }
    }
    'Status' {
        try {
            $Query = schtasks /Query /TN $TaskName /V /FO LIST 2>$null
            if ($?) {
                Write-Host "Status: $($Query.Trim())" -ForegroundColor Yellow
            } else {
                Write-Host "Task '$TaskName' not registered." -ForegroundColor Cyan
            }
        } catch {
            Write-Error $_.Exception.Message
            exit 1
        }
    }
}