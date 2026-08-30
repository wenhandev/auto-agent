#!/usr/bin/env bash
# Copy PyInstaller onedir sidecar into the Tauri bundle layout for release builds.
# Usage: ./worker/stage-client-sidecar.sh
# Output: client/src-tauri/binaries/runtime-{target-triple}/

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/backend/dist/auto-agent-worker"
DEST_ROOT="${ROOT}/client/src-tauri/binaries"

if [[ ! -f "${SRC}/auto-agent-worker" ]]; then
  echo "Missing sidecar bundle at ${SRC}/auto-agent-worker — run worker/build-*.sh first." >&2
  exit 1
fi

TRIPLE="$(rustc -Vv | sed -n 's/^host: //p')"
if [[ -z "${TRIPLE}" ]]; then
  echo "Could not detect Rust target triple (rustc -Vv)." >&2
  exit 1
fi

DEST="${DEST_ROOT}/runtime-${TRIPLE}"
rm -rf "${DEST}"
mkdir -p "${DEST}"
cp -a "${SRC}/." "${DEST}/"
chmod +x "${DEST}/auto-agent-worker"


cp "${DEST}/auto-agent-worker" "${DEST_ROOT}/auto-agent-runtime-${TRIPLE}"
chmod +x "${DEST_ROOT}/auto-agent-runtime-${TRIPLE}"
echo "Staged externalBin → ${DEST_ROOT}/auto-agent-runtime-${TRIPLE}"

echo "Staged sidecar for ${TRIPLE} → ${DEST}"
