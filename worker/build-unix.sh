#!/usr/bin/env bash
# Build auto-agent-worker on macOS or Linux (PyInstaller onedir bundle).
# Usage: ./worker/build-unix.sh
# Output: backend/dist/auto-agent-worker/auto-agent-worker

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/backend"
DIST_BIN="${BACKEND}/dist/auto-agent-worker/auto-agent-worker"

cd "${BACKEND}"
python -m pip install -e ".[worker-build]"
python -m PyInstaller "${ROOT}/worker/auto-agent-worker.spec" --noconfirm --clean

chmod +x "${DIST_BIN}"

echo ""
echo "Built: ${DIST_BIN}"
echo "Zip the whole dist/auto-agent-worker folder for distribution."
echo "After install, run once: ./auto-agent-worker install-browsers"
