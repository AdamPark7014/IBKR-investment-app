#Requires -Version 5.1
<#
.SYNOPSIS
  Registra, quita o consulta la tarea del vigía: cada 15 minutos revisa si falta el plan o la ejecución
  del día y corre lo que falte.
.NOTES
  Sustituye a las tareas de hora fija (plan y ejecución): al registrar el vigía se desactivan, y al
  quitarlo se vuelven a activar. La tarea de latido (heartbeat-check) no se toca.
  No cambia nada de la configuración de inversión: llama a los mismos `run-daily --phase plan|execute`.
#>
param(
    [ValidateSet('Register', 'Unregister', 'Status')]
    [string]$Action = 'Status',
    [int]$EveryMinutes = 15
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Name = 'ibtrader-vigia'
$Fixed = @('ibtrader-run-daily-plan', 'ibtrader-run-daily-execute')

switch ($Action) {
    'Register' {
        $Runner = Join-Path $RepoRoot 'scripts\run-task.ps1'
        $Ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $Tr = "`"$Ps`" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Runner`" -Name $Name -Command `"vigia`""
        if ($Tr.Length -gt 261) { Write-Error "La orden de la tarea pasa de 261 caracteres (límite de schtasks)."; exit 1 }
        schtasks /Create /TN $Name /TR $Tr /SC MINUTE /MO $EveryMinutes /F
        if ($LASTEXITCODE -ne 0) { Write-Error "schtasks /Create $Name falló ($LASTEXITCODE)."; exit $LASTEXITCODE }
        $Task = Get-ScheduledTask -TaskName $Name
        $Task.Settings.DisallowStartIfOnBatteries = $false
        $Task.Settings.StopIfGoingOnBatteries = $false
        $Task.Settings.StartWhenAvailable = $true
        $Task.Settings.MultipleInstances = 'IgnoreNew'
        Set-ScheduledTask -InputObject $Task | Out-Null
        # Sin ventana (26-11-2026): con Windows Terminal como consola, -WindowStyle Hidden igual deja Terminal visible
        # toda la corrida, cada 15 min. El lanzador de C:\dev conserva comillas y código de salida.
        $SinVentana = 'C:\dev\scripts\ai-os\tools\tarea-sin-ventana.ps1'
        if (Test-Path -LiteralPath $SinVentana) { & $SinVentana -Nombre $Name | Out-Null }
        foreach ($f in $Fixed) {
            schtasks /Change /TN $f /DISABLE 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "Desactivada '$f' (la sustituye el vigía)." }
        }
        Write-Host "Registrada '$Name' cada $EveryMinutes minutos."
    }
    'Unregister' {
        schtasks /Delete /TN $Name /F 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "Tarea '$Name' no encontrada (OK)." } else { Write-Host "Eliminada '$Name'." }
        foreach ($f in $Fixed) {
            schtasks /Change /TN $f /ENABLE 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "Reactivada '$f'." }
        }
    }
    'Status' {
        schtasks /Query /TN $Name /FO LIST 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "Tarea '$Name' no registrada." }
    }
}
exit 0
