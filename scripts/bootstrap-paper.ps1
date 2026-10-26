#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot PAPER triage bootstrap: config freeze + paper-status.
.NOTES
  PAPER triage only — zero broker orders — NO LIVE.
  Does NOT Register Task Scheduler (Adam does that via schedule-register-all.ps1).
  No sample data goes into data/: data/paper_open_orders.json is for real paper orders only
  (`ibtrader open-orders --write-sample` writes data/paper_open_orders.sample.json, ignored by triage).
  config-freeze --write refuses to overwrite a freeze whose config changed (exit 1): that is drift.
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
