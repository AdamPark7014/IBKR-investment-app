#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Status', 'RunOnce')] [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Write-Host 'PAPER triage only — zero broker orders — NO LIVE.'

if ($Action -eq 'Status') {
    Write-Host "=== ibtrader-autopilot ===" -ForegroundColor Cyan
    & "$PSScriptRoot\schedule-autopilot.ps1" -Action Status 2>&1 | Out-Null
    
    Write-Host "=== ibtrader-paper-reconcile ===" -ForegroundColor Cyan
    & "$PSScriptRoot\schedule-reconcile.ps1" -Action Status 2>&1 | Out-Null
    
    Write-Host "=== ibtrader-ibc-check ===" -ForegroundColor Cyan
    & "$PSScriptRoot\schedule-ibc-check.ps1" -Action Status 2>&1 | Out-Null

    exit 0
}

if ($Action -eq 'RunOnce') {
    $VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    
    # Prefer venv python, then path, else error
    if (Test-Path $VenvPy) {
        $Cmds = @(
            "ibtrader.ops.cli ibc-checklist",
            "ibtrader.ops.cli paper-reconcile",
            "ibtrader.ops.cli paper-vs-oos",
            "ibtrader.ops.cli paper-stack"
        )
    } elseif ($null -ne (Get-Command ibtrader.ops.cli -ErrorAction SilentlyContinue)) {
        $Cmds = @(
            "ibc-checklist",
            "paper-reconcile",
            "paper-vs-oos",
            "paper-stack"
        )
    } else {
        Write-Error "Could not find Python CLI for triage."
        exit 1
    }

    $ExitCode = 0
    foreach ($Cmd in $Cmds) {
        Write-Host "=== $Cmd ===" -ForegroundColor Cyan
        try {
            & ibtrader.ops.cli $Cmd
        } catch {
            # Catch errors but continue
        }
        
        $LastExitCode = $LASTEXITCODE
        if ($LastExitCode -ne 0) {
            Write-Warning "Command '$Cmd' returned exit code $LastExitCode"
            $ExitCode = [int]$LastExitCode
        }
    }

    if ($ExitCode -eq 0) {
        Write-Host "Triage completed successfully." -ForegroundColor Green
        exit 0
    } else {
        Write-Warning "Triage completed with errors (exit code $ExitCode)."
        exit $ExitCode
    }
}
</script>