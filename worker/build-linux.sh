#!/usr/bin/env bash
# Build auto-agent-worker on Linux (PyInstaller onedir bundle).
# Usage: ./worker/build-linux.sh
exec "$(dirname "${BASH_SOURCE[0]}")/build-unix.sh"
