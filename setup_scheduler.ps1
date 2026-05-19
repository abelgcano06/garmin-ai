# Ejecutar como Administrador
# Registra ApexGarminSync para correr cada 2 horas

$action   = New-ScheduledTaskAction -Execute "C:\garmin-ai\scheduled_sync.bat"
$trigger  = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At (Get-Date)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest

Register-ScheduledTask `
    -TaskName "ApexGarminSync" `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host "[OK] Tarea 'ApexGarminSync' registrada. Sync cada 2 horas." -ForegroundColor Green
Write-Host "  Puedes verla en: Programador de tareas -> ApexGarminSync" -ForegroundColor Cyan
