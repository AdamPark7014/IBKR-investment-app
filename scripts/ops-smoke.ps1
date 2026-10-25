#Requires -Version 5.1
<#
.SYNOPSIS
  Paper ops smoke: Status of scheduled triage tasks, or RunOnce CLI paper checks.
.NOTES
  PAPER triage only — zero broker orders — NO LIVE trading.
#>
param(
    [ValidateSet('Status', 'RunOnce')]
    [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Write-Host 'PAPER triage only — zero broker orders — NO LIVE.'

switch ($Action) {
    'Status' {
        Write-Host '=== ibtrader-autopilot ==='
        & (Join-Path $PSScriptRoot 'schedule-autopilot.ps1') -Action Status
        Write-Host '=== ibtrader-paper-reconcile ==='
        & (Join-Path $PSScriptRoot 'schedule-reconcile.ps1') -Action Status
        Write-Host '=== ibtrader-ibc-check ==='
        & (Join-Path $PSScriptRoot 'schedule-ibc-check.ps1') -Action Status
        exit 0
    }
    'RunOnce' {
        $VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
        $useVenv = Test-Path -LiteralPath $VenvPy
        if (-not $useVenv -and -not (Get-Command ibtrader -ErrorAction SilentlyContinue)) {
            Write-Error "Need repo .venv\Scripts\python.exe or ibtrader on PATH. Repo=$RepoRoot"
            exit 1
        }

        $cmds = @('ibc-checklist', 'paper-reconcile', 'paper-vs-oos', 'paper-stack')
        $failed = @()
        foreach ($cmd in $cmds) {
            Write-Host "=== $cmd ==="
            if ($useVenv) {
                & $VenvPy -m ibtrader.ops.cli $cmd
            }
            else {
                & ibtrader $cmd
            }
            $code = $LASTEXITCODE
            if ($null -eq $code) { $code = 0 }
            if ($code -ne 0) {
                Write-Warning "$cmd exited $code (continuing)."
                $failed += "$cmd=$code"
            }
        }

        Write-Host '=== PAPER triage summary ==='
        if ($failed.Count -eq 0) {
            Write-Host 'All checks exited 0.'
            exit 0
        }
        Write-Host ("Failures: " + ($failed -join ', '))
        exit 1
    }
}
