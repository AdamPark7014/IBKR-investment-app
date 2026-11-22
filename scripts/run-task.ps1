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
# Los logs se escriben en UTF-8. Uno viejo en UTF-16 (lo que dejaba `*>>` en PowerShell 5.1) se aparta
# una vez para no mezclar codificaciones en el mismo archivo.
if (Test-Path -LiteralPath $log) {
    $head = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $log)) | Select-Object -First 2
    if ($head.Count -eq 2 -and $head[0] -eq 0xFF -and $head[1] -eq 0xFE) {
        Move-Item -LiteralPath $log -Destination (Join-Path 'data\logs' "$Name.utf16-$(Get-Date -Format yyyyMMdd).log") -Force
    }
}

$tokenFile = $env:IBTRADER_PUERTA_TOKEN_FILE
if (-not $tokenFile) { $tokenFile = 'C:\dev\secrets\puerta-ia\ibkr.token' }
if (Test-Path -LiteralPath $tokenFile) {
    $env:ANTHROPIC_API_KEY = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
    $env:ANTHROPIC_BASE_URL = $BaseUrl
} else {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format s) sin token de la puerta ($tokenFile): Claude apagado"
}

$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$cmdArgs = $Command -split ' '
# stderr se junta con stdout como texto plano: `*>>` convertía cada línea de stderr de Python en un
# `NativeCommandError` de PowerShell con su traza, y el log se llenaba de ruido.
$ErrorActionPreference = 'Continue'
if (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy -m ibtrader.ops.cli @cmdArgs 2>&1 | ForEach-Object { "$_" } | Add-Content -LiteralPath $log -Encoding UTF8
} elseif (Get-Command ibtrader -ErrorAction SilentlyContinue) {
    & ibtrader @cmdArgs 2>&1 | ForEach-Object { "$_" } | Add-Content -LiteralPath $log -Encoding UTF8
} else {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format s) falta .venv\Scripts\python.exe o ibtrader en PATH"
    exit 1
}
exit $LASTEXITCODE
