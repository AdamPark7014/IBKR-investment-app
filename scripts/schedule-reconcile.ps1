#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query a daily Windows Task Scheduler job for ibtrader paper-reconcile.
.NOTES
  PAPER triage only — zero broker orders — NO LIVE trading.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [string]$Time = '16:35'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ibtrader-paper-reconcile'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Write-Host 'PAPER triage only — zero broker orders — NO LIVE.'

switch ($Action) {
    'Register' {
        $VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $VenvPy) {
            $inner = "Set-Location -LiteralPath '$RepoRoot'; & '$VenvPy' -m ibtrader.ops.cli paper-reconcile"
        }
        elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
            $inner = "Set-Location -LiteralPath '$RepoRoot'; & ibtrader paper-reconcile"
        }
        else {
            Write-Error "Need repo .venv\Scripts\python.exe or ibtrader on PATH. Repo=$RepoRoot"
            exit 1
        }

        # WorkingDirectory = repo via Set-Location inside -Command. /F = idempotent recreate.
        $Tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"$inner`""
        schtasks /Create /TN $TaskName /TR $Tr /SC DAILY /ST $Time /F
        if ($LASTEXITCODE -ne 0) {
            Write-Error "schtasks /Create failed (exit $LASTEXITCODE)."
            exit $LASTEXITCODE
        }
        Write-Host "Registered '$TaskName' daily at $Time. WorkingDirectory=$RepoRoot"
    }
    'Unregister' {
        schtasks /Delete /TN $TaskName /F 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Task '$TaskName' not found (OK)."
            exit 0
        }
        Write-Host "Unregistered '$TaskName'."
    }
    'Status' {
        schtasks /Query /TN $TaskName /V /FO LIST 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Task '$TaskName' not registered."
            exit 0
        }
    }
}
