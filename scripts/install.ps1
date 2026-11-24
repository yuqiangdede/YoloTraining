param(
    [Parameter(Mandatory = $true)]
    [string]$OfflineResourceRoot,
    [switch]$SkipFrontend,
    [string]$RfDetrWheelDir
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$TorchRoot = Get-ChildItem -Path $OfflineResourceRoot -Directory | Where-Object { $_.Name -like 'PyTorch*' } | Select-Object -First 1
$PlatformRoot = Get-ChildItem -Path $OfflineResourceRoot -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'ultralytics-8.4.92-*.whl') } | Select-Object -First 1
if (-not $TorchRoot) { throw 'Cannot locate the PyTorch offline package directory.' }
if (-not $PlatformRoot) { throw 'Cannot locate the YOLO platform wheel directory.' }
$TorchWheels = Join-Path $TorchRoot.FullName 'cu124-py311'
$PlatformWheels = $PlatformRoot.FullName

if (-not (Test-Path $VenvPython)) {
    py -3.11 -m venv (Join-Path $ProjectRoot '.venv')
}

& $VenvPython -m pip install --no-index --find-links=$TorchWheels torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124
& $VenvPython -m pip install --no-index --find-links=$PlatformWheels -r (Join-Path $ProjectRoot 'backend\requirements-base.txt')
& $VenvPython -m pip install --no-index --find-links=$PlatformWheels ultralytics==8.4.92 onnx==1.22.0 onnxslim==0.1.94 onnxruntime==1.27.0

if ($RfDetrWheelDir) {
    $RfDetrWheels = (Resolve-Path -LiteralPath $RfDetrWheelDir).Path
    Write-Host '正在离线安装 RF-DETR 训练依赖…'
    & $VenvPython -m pip install --no-index --find-links=$RfDetrWheels -r (Join-Path $ProjectRoot 'backend\requirements-rfdetr.txt')
    if ($LASTEXITCODE -ne 0) { throw 'RF-DETR 依赖安装失败。' }
}

if (-not $SkipFrontend) {
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try {
        npm install
        npm run build
    }
    finally { Pop-Location }
}

Write-Host 'Installation complete. Runtime dependencies are project-local.'
