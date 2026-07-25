param(
    [string]$OfflineResourceRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'resources\offline'),
    [ValidateSet('n','s','m','l','x')][string[]]$Scales = @('n'),
    [ValidateSet('pt','onnx')][string[]]$Formats = @('pt'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Archive = Join-Path $OfflineResourceRoot 'YOLO26-models'
$ProjectModels = Join-Path $ProjectRoot 'models\pretrained'
New-Item -ItemType Directory -Path $Archive -Force | Out-Null
New-Item -ItemType Directory -Path $ProjectModels -Force | Out-Null
$Suffixes = @('', '-seg', '-sem', '-pose', '-obb')

function Download-Model([string]$Name, [string]$Destination) {
    $Uri = "https://github.com/ultralytics/assets/releases/download/v8.4.0/$Name"
    if ($Force -or -not (Test-Path $Destination)) {
        Write-Host "Downloading $Name ..."
        Invoke-WebRequest -Uri $Uri -OutFile $Destination
    }
    $Length = (Get-Item $Destination).Length
    if ($Length -le 0) { throw "Downloaded file is empty: $Destination" }
    Get-FileHash -Path $Destination -Algorithm SHA256 | Select-Object Path,Hash
}

foreach ($Scale in $Scales) {
    foreach ($Suffix in $Suffixes) {
        foreach ($Format in $Formats) {
            $Name = "yolo26$Scale$Suffix.$Format"
            $Archived = Join-Path $Archive $Name
            Download-Model -Name $Name -Destination $Archived
            Copy-Item -Path $Archived -Destination (Join-Path $ProjectModels $Name) -Force
        }
    }
}

Write-Host "Models are cached under $Archive and copied to $ProjectModels."
