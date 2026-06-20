#!/usr/bin/env bash
# Upload client installers to the production VM (free static hosting at /downloads/).
#
# Usage:
#   ./deploy/publish-client-downloads.sh                          # from deploy/downloads/
#   ./deploy/publish-client-downloads.sh /path/to/release-assets
#
# Expects these filenames (stable URLs on /client):
#   Auto-Agent-Client-macos.dmg
#   Auto-Agent-Client-windows.msi
#   Auto-Agent-Client-linux.AppImage

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-${ROOT}/deploy/downloads}"
PROJECT="${GCP_PROJECT:-auto-agent-500007}"
VM="${GCP_VM:-auto-agent-rpa}"
ZONE="${GCP_ZONE:-asia-east1-b}"
REMOTE="/opt/auto-agent/deploy/downloads"

shopt -s nullglob
files=("${SRC}"/Auto-Agent-Client-*.{dmg,msi,AppImage})
if [[ ${#files[@]} -eq 0 ]]; then
  echo "No installers in ${SRC} (Auto-Agent-Client-*.{dmg,msi,AppImage})" >&2
  exit 1
fi

echo "Uploading ${#files[@]} file(s) to ${VM}:${REMOTE} …"
gcloud compute ssh "${VM}" --project="${PROJECT}" --zone="${ZONE}" \
  --command="mkdir -p ${REMOTE} && chmod 755 ${REMOTE}"

for f in "${files[@]}"; do
  gcloud compute scp "${f}" "${VM}:${REMOTE}/" --project="${PROJECT}" --zone="${ZONE}"
  echo "  → $(basename "${f}")"
done

gcloud compute ssh "${VM}" --project="${PROJECT}" --zone="${ZONE}" \
  --command="ls -lh ${REMOTE} && cd /opt/auto-agent/deploy && sudo docker compose restart caddy"

echo ""
echo "Public URLs:"
echo "  https://rpa.wenhandev.com/downloads/Auto-Agent-Client-macos.dmg"
echo "  https://rpa.wenhandev.com/downloads/Auto-Agent-Client-windows.msi"
echo "  https://rpa.wenhandev.com/downloads/Auto-Agent-Client-linux.AppImage"
