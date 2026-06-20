# Copy PyInstaller onedir sidecar into the Tauri bundle layout for release builds.
# Usage: .\worker\stage-client-sidecar.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Src = Join-Path $Root "backend\dist\auto-agent-worker\auto-agent-worker.exe"
$DestRoot = Join-Path $Root "client\src-tauri\binaries"

if (-not (Test-Path $Src)) {
  throw "Missing sidecar at $Src — run worker\build-exe.ps1 first."
}

$TripleLine = (rustc -Vv | Select-String "^host: ").Line
if (-not $TripleLine) {
  throw "Could not detect Rust target triple (rustc -Vv)."
}
$Triple = $TripleLine -replace "^host: ", ""

$Dest = Join-Path $DestRoot "runtime-$Triple"
if (Test-Path $Dest) {
  Remove-Item -Recurse -Force $Dest
}
New-Item -ItemType Directory -Path $Dest -Force | Out-Null
Copy-Item -Path (Join-Path $Root "backend\dist\auto-agent-worker\*") -Destination $Dest -Recurse -Force

Write-Host "Staged sidecar for $Triple → $Dest"
