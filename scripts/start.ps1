param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$PidFile = Join-Path $ProjectRoot 'data\server.pid'

if (-not (Test-Path $Python)) { throw 'Project-local .venv is missing. Run scripts\install.ps1 first.' }
if (Test-Path $PidFile) {
    $ExistingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) { throw "Server is already running, PID: $ExistingPid" }
}

$env:PYTHONPATH = Join-Path $ProjectRoot 'backend'
$env:YOLO_CONFIG_DIR = Join-Path $ProjectRoot 'resources'
$Process = Start-Process -FilePath $Python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory (Join-Path $ProjectRoot 'backend') -RedirectStandardOutput (Join-Path $ProjectRoot 'logs\api.log') -RedirectStandardError (Join-Path $ProjectRoot 'logs\api-error.log') -WindowStyle Hidden -PassThru
$Process.Id | Set-Content $PidFile -Encoding ascii
Start-Sleep -Seconds 2
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8000' }
Write-Host "视觉模型训练台已启动：http://127.0.0.1:8000 (PID $($Process.Id))"
