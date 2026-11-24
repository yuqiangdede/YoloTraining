param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [switch]$Confirm
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupFullPath = [IO.Path]::GetFullPath($BackupPath)
if (-not $Confirm) { throw 'Restore is destructive. Re-run with -Confirm after stopping active work.' }
if (-not (Test-Path -LiteralPath $BackupFullPath) -or [IO.Path]::GetExtension($BackupFullPath) -ne '.zip') { throw 'Backup archive was not found.' }

$PidFile = Join-Path $ProjectRoot 'data\server.pid'
if (Test-Path $PidFile) { & (Join-Path $PSScriptRoot 'stop.ps1') }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Stage = Join-Path $ProjectRoot ("backups\.restore-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
try {
    $StageFullPath = [IO.Path]::GetFullPath($Stage) + [IO.Path]::DirectorySeparatorChar
    $Archive = [IO.Compression.ZipFile]::OpenRead($BackupFullPath)
    try {
        foreach ($Entry in $Archive.Entries) {
            $Target = [IO.Path]::GetFullPath((Join-Path $Stage $Entry.FullName))
            if (-not $Target.StartsWith($StageFullPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup contains an unsafe path.' }
        }
    }
    finally { $Archive.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($BackupFullPath, $Stage)
    $Manifest = Join-Path $Stage 'backup-manifest.json'
    if (-not (Test-Path $Manifest)) { throw 'Backup manifest is missing.' }
    $ManifestData = Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json
    if (@('vision-model-studio-backup/v1', 'yolo26-studio-backup/v1') -notcontains $ManifestData.format) { throw 'Unsupported backup format.' }

    $Safety = Join-Path $ProjectRoot ("backups\pre-restore-" + (Get-Date -Format 'yyyyMMddTHHmmss'))
    New-Item -ItemType Directory -Path $Safety -Force | Out-Null
    $Directories = @('data', 'uploads', 'models', 'runs', 'resources')
    foreach ($Directory in $Directories) {
        $Current = Join-Path $ProjectRoot $Directory
        if (Test-Path $Current) { Copy-Item -Path $Current -Destination (Join-Path $Safety $Directory) -Recurse -Force }
        $Restored = Join-Path $Stage $Directory
        if (Test-Path $Restored) {
            if (Test-Path $Current) { Remove-Item -LiteralPath $Current -Recurse -Force }
            Copy-Item -Path $Restored -Destination $Current -Recurse -Force
        }
    }
    Write-Host "Restore complete. Previous data was saved to $Safety. Start the service again with scripts\start.ps1."
}
finally {
    if (Test-Path $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
