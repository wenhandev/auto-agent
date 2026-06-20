#!/usr/bin/env bash
# macOS codesign + notarize stub for Auto Agent desktop builds.
#
# Required environment variables (set in CI secrets or locally):
#   APPLE_SIGNING_IDENTITY  — e.g. "Developer ID Application: Your Org (TEAMID)"
#   APPLE_ID              — Apple ID email for notarization
#   APPLE_APP_PASSWORD    — app-specific password
#   APPLE_TEAM_ID         — 10-character team id
#
# Optional:
#   TAURI_APP_PATH        — path to .app bundle (default: newest under bundle/macos)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUNDLE_DIR="${ROOT}/client/src-tauri/target/release/bundle/macos"

if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  echo "APPLE_SIGNING_IDENTITY is not set — skipping codesign."
  echo "See client/README.md for optional macOS signing env vars."
  exit 0
fi

APP_PATH="${TAURI_APP_PATH:-}"
if [[ -z "${APP_PATH}" ]]; then
  APP_PATH="$(find "${BUNDLE_DIR}" -maxdepth 1 -name '*.app' -print -quit || true)"
fi

if [[ -z "${APP_PATH}" || ! -d "${APP_PATH}" ]]; then
  echo "No .app bundle found under ${BUNDLE_DIR}"
  exit 1
fi

echo "Codesigning ${APP_PATH} with ${APPLE_SIGNING_IDENTITY}"
codesign --force --options runtime --deep --sign "${APPLE_SIGNING_IDENTITY}" "${APP_PATH}"
codesign --verify --verbose=2 "${APP_PATH}"

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  DMG_PATH="$(find "${BUNDLE_DIR}" -maxdepth 1 -name '*.dmg' -print -quit || true)"
  if [[ -n "${DMG_PATH}" ]]; then
    echo "Notarizing ${DMG_PATH}"
    xcrun notarytool submit "${DMG_PATH}" \
      --apple-id "${APPLE_ID}" \
      --password "${APPLE_APP_PASSWORD}" \
      --team-id "${APPLE_TEAM_ID}" \
      --wait
    xcrun stapler staple "${DMG_PATH}"
  fi
else
  echo "Notarization skipped (set APPLE_ID, APPLE_APP_PASSWORD, APPLE_TEAM_ID to enable)."
fi

echo "Done."
