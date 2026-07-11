$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$env:YOLO_CONFIG_DIR = Join-Path $ProjectRoot 'resources'
Write-Host "Project root: $ProjectRoot"
Write-Host "Project-local venv: $(Test-Path $Python)"
if (Test-Path $Python) {
    & $Python -c "import sys, torch, ultralytics; print('Python:', sys.version.split()[0]); print('PyTorch:', torch.__version__); print('Ultralytics:', ultralytics.__version__); print('CUDA available:', torch.cuda.is_available()); print('CUDA runtime:', torch.version.cuda); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
}
Write-Host 'Pretrained models:'
Get-ChildItem (Join-Path $ProjectRoot 'models\pretrained') -Filter '*.pt' -ErrorAction SilentlyContinue | Select-Object Name,Length
Write-Host 'Disk space:'
Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($ProjectRoot).TrimEnd(':\')) | Select-Object Name,Used,Free
