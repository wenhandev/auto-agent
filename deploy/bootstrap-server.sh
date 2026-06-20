#!/usr/bin/env bash
# One-shot remote bootstrap for rpa.wenhandev.com (Ubuntu/Debian VPS).
set -euo pipefail

DOMAIN="${DOMAIN:-rpa.wenhandev.com}"
REPO_DIR="${REPO_DIR:-/opt/auto-agent}"
BRANCH="${BRANCH:-main}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (or via sudo)." >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

mkdir -p "$REPO_DIR"
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" fetch --all
  git -C "$REPO_DIR" checkout "$BRANCH"
  git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
else
  echo "Clone your repo into $REPO_DIR first, e.g.:"
  echo "  git clone <your-repo-url> $REPO_DIR"
  exit 1
fi

cd "$REPO_DIR/deploy"

if [[ ! -f .env ]]; then
  cp .env.production.example .env
  echo ""
  echo "Created deploy/.env — edit SESSION_SECRET and ADMIN_PASSWORD, then re-run:"
  echo "  nano $REPO_DIR/deploy/.env"
  exit 0
fi

docker compose build --pull
docker compose up -d

echo ""
echo "Deployed. Point DNS A record for $DOMAIN to this server, then open:"
echo "  https://$DOMAIN"
echo ""
echo "Admin login: credentials from deploy/.env (ADMIN_EMAIL / ADMIN_PASSWORD)"
echo "Desktop clients: set cloud URL to https://$DOMAIN"
