#Requires -Version 5.1
<#
.SYNOPSIS
  Ejecuta un comando de ibtrader desde una tarea programada: carga el token de la puerta de Claude,
  entra al repo y guarda la salida en data\logs\<Name>.log.
.NOTES
  El token de la puerta NO va en .env (AppSettings rechaza claves desconocidas): se lee de un archivo
  fuera del repo. Por defecto C:\dev\secrets\puerta-ia\ibkr.token; se cambia con la variable de entorno
  IBTRADER_PUERTA_TOKEN_FILE. Sin archivo, el sistema corre igual y Claude (copiloto/triage) queda apagado.
#>
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Command,
    [string]$BaseUrl = 'https://ia.zynoratek.com'
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $RepoRoot
New-Item -ItemType Directory -Force 'data\logs' | Out-Null
$log = Join-Path 'data\logs' "$Name.log"

$tokenFile = $env:IBTRADER_PUERTA_TOKEN_FILE
if (-not $tokenFile) { $tokenFile = 'C:\dev\secrets\puerta-ia\ibkr.token' }
if (Test-Path -LiteralPath $tokenFile) {
    $env:ANTHROPIC_API_KEY = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
    $env:ANTHROPIC_BASE_URL = $BaseUrl
} else {
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format s) sin token de la puerta ($tokenFile): Claude apagado"
}

$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$cmdArgs = $Command -split ' '
if (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy -m ibtrader.ops.cli @cmdArgs *>> $log
} elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
    & ibtrader @cmdArgs *>> $log
} else {
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format s) falta .venv\Scripts\python.exe o ibtrader en PATH"
    exit 1
}
exit $LASTEXITCODE
