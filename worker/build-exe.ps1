# Build auto-agent-worker.exe on Windows (PyInstaller onedir bundle).
# Usage: .\worker\build-exe.ps1
# Output: backend\dist\auto-agent-worker\auto-agent-worker.exe

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"

Push-Location $Backend
try {
    python -m pip install -e ".[worker-build]"
    python -m PyInstaller (Join-Path $Root "worker\auto-agent-worker.spec") --noconfirm --clean
    Write-Host ""
    Write-Host "Built: $Backend\dist\auto-agent-worker\auto-agent-worker.exe"
    Write-Host "Zip the whole dist\auto-agent-worker folder for distribution."
    Write-Host "After install, run once: auto-agent-worker install-browsers"
} finally {
    Pop-Location
}
