$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot 'data\server.pid'
if (-not (Test-Path $PidFile)) { Write-Host 'No running server was recorded.'; exit 0 }
$ServerPid = Get-Content $PidFile -ErrorAction SilentlyContinue
if ($ServerPid) { Stop-Process -Id $ServerPid -ErrorAction SilentlyContinue }
Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
Write-Host '视觉模型训练台已停止。'
