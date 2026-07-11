param(
    [Parameter(Mandatory = $true)][string]$OfflineResourceRoot,
    [ValidateSet('n','s','m','l','x')][string[]]$Scales = @('n')
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Archive = Join-Path $OfflineResourceRoot 'YOLO26-models'
$ProjectModels = Join-Path $ProjectRoot 'models\pretrained'
New-Item -ItemType Directory -Path $Archive -Force | Out-Null
New-Item -ItemType Directory -Path $ProjectModels -Force | Out-Null
$Suffixes = @('', '-seg', '-sem', '-pose', '-obb')
foreach ($Scale in $Scales) {
    foreach ($Suffix in $Suffixes) {
        $Name = "yolo26$Scale$Suffix.pt"
        $Archived = Join-Path $Archive $Name
        if (-not (Test-Path $Archived)) {
            Invoke-WebRequest -Uri "https://github.com/ultralytics/assets/releases/download/v8.4.0/$Name" -OutFile $Archived
        }
        Copy-Item -Path $Archived -Destination (Join-Path $ProjectModels $Name) -Force
        Get-FileHash -Path $Archived -Algorithm SHA256 | Select-Object Path,Hash
    }
}
