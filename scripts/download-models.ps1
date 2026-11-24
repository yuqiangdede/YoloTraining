param(
    [string]$OfflineResourceRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'resources\offline'),
    [ValidateSet('n','s','m','l','x')][string[]]$Scales = @('n'),
    [ValidateSet('pt','onnx')][string[]]$Formats = @('pt'),
    [switch]$Force,
    [switch]$RfDetr,
    [ValidateSet('nano','small','medium','large')][string[]]$RfDetrSizes = @('nano')
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Archive = Join-Path $OfflineResourceRoot 'YOLO26-models'
$ProjectModels = Join-Path $ProjectRoot 'models\pretrained'
if ($RfDetr) {
    $Cache = 'D:\cache\models'
    # 与 RF-DETR 1.12.1 注册表保持一致，Large 使用当前架构的 2026 权重。
    $Registry = @{
        nano = @{ Name = 'rf-detr-nano.pth'; Asset = 'nano_coco/checkpoint_best_regular.pth'; MD5 = 'fb6504cce7fbdc783f7a46991f07639f' }
        small = @{ Name = 'rf-detr-small.pth'; Asset = 'small_coco/checkpoint_best_regular.pth'; MD5 = 'fb37061c1af7bace359c91b723a8d5c1' }
        medium = @{ Name = 'rf-detr-medium.pth'; Asset = 'medium_coco/checkpoint_best_regular.pth'; MD5 = '7223f764a87b863f02eb8d52bf0ce2ee' }
        large = @{ Name = 'rf-detr-large-2026.pth'; Asset = 'rf-detr-large-2026.pth'; MD5 = '5cb72153541cbcb9aa6efa26222acc75' }
    }
    New-Item -ItemType Directory -Path $Cache -Force | Out-Null
    $Destination = Join-Path $ProjectModels 'rfdetr'
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($Size in $RfDetrSizes) {
        $Model = $Registry[$Size]
        $Cached = Join-Path $Cache $Model.Name
        if ($Force -or -not (Test-Path -LiteralPath $Cached) -or (Get-FileHash -LiteralPath $Cached -Algorithm MD5).Hash -ne $Model.MD5) {
            $Partial = "$Cached.$PID.download"
            try {
                Write-Host "正在下载 RF-DETR $Size 权重…"
                Invoke-WebRequest -Uri "https://repo.roboflow.com/rfdetr/$($Model.Asset)" -OutFile $Partial
                if ((Get-FileHash -LiteralPath $Partial -Algorithm MD5).Hash -ne $Model.MD5) { throw "RF-DETR $Size 权重校验失败。" }
                Move-Item -LiteralPath $Partial -Destination $Cached -Force
            }
            finally {
                if (Test-Path -LiteralPath $Partial) { Remove-Item -LiteralPath $Partial }
            }
        }
        Copy-Item -LiteralPath $Cached -Destination (Join-Path $Destination $Model.Name) -Force
        Write-Host "RF-DETR $Size 权重已校验并复制到项目。"
    }
    return
}
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
