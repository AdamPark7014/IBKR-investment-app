#Requires -Version 5.1
<#
.SYNOPSIS
  Register / unregister / query / run-once a daily Windows Task Scheduler job for ibtrader ibc-checklist.
.NOTES
  PAPER triage only — zero broker orders — NO LIVE trading.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status', 'RunOnce')]
    [string]$Action = 'Status',
    [string]$Time = '08:00'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ibtrader-ibc-check'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Write-Host 'PAPER triage only — zero broker orders — NO LIVE.'

function Get-IbtraderInner {
    $VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $VenvPy) {
        return "Set-Location -LiteralPath '$RepoRoot'; & '$VenvPy' -m ibtrader.ops.cli ibc-checklist"
    }
    elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
        return "Set-Location -LiteralPath '$RepoRoot'; & ibtrader ibc-checklist"
    }
    else {
        Write-Error "Need repo .venv\Scripts\python.exe or ibtrader on PATH. Repo=$RepoRoot"
        exit 1
    }
}

switch ($Action) {
    'Register' {
        $inner = Get-IbtraderInner
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
    'RunOnce' {
        $inner = Get-IbtraderInner
        Invoke-Expression $inner
        exit $LASTEXITCODE
    }
}
