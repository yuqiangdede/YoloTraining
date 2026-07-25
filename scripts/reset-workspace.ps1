param([switch]$Confirm)

if (-not $Confirm) {
    throw '此操作会永久清空工作数据。请使用 .\scripts\reset-workspace.ps1 -Confirm 确认。'
}

$root = Split-Path -Parent $PSScriptRoot
$targets = @('data\studio.db', 'uploads\assets', 'data\datasets', 'runs', 'models\trained', 'logs', 'backups')
foreach ($relative in $targets) {
    $path = Join-Path $root $relative
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    if ([IO.Path]::GetExtension($path)) { continue }
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}
Write-Host '工作数据已清空；源码、预训练模型和依赖未受影响。'
