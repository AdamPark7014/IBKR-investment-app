#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot PAPER triage bootstrap: sample open-orders, config freeze, paper-status.
.NOTES
  PAPER triage only — zero broker orders — NO LIVE.
  Does NOT Register Task Scheduler (Adam does that via schedule-register-all.ps1).
#>
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'

Write-Host 'PAPER triage only — zero broker orders — NO LIVE.'
Write-Host 'Does NOT Register Task Scheduler (Adam does that).'

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Error "Need repo .venv\Scripts\python.exe. Repo=$RepoRoot"
    exit 1
}

$cmds = @(
    @('open-orders', '--write-sample'),
    @('config-freeze', '--write'),
    @('paper-status')
)

$failed = @()
foreach ($cliArgs in $cmds) {
    $label = $cliArgs -join ' '
    Write-Host "=== $label ==="
    & $VenvPy -m ibtrader.ops.cli @cliArgs
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
        Write-Warning "$label exited $code (continuing)."
        $failed += "$label=$code"
    }
}

Write-Host '=== bootstrap-paper summary ==='
if ($failed.Count -eq 0) {
    Write-Host 'All steps exited 0. Schedules: use schedule-register-all.ps1 separately.'
    exit 0
}
Write-Host ("Failures: " + ($failed -join ', '))
exit 1
