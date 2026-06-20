#!/usr/bin/env bash
# Build auto-agent-worker on macOS (PyInstaller onedir bundle).
# Usage: ./worker/build-macos.sh
exec "$(dirname "${BASH_SOURCE[0]}")/build-unix.sh"
