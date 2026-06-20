# Cloud deployment — rpa.wenhandev.com

GCP project: **`auto-agent-500007`** · VM: **`auto-agent-rpa`** · region **`asia-east1-b`**

Deploy the **control plane only** (`EXECUTION_BACKEND=control_plane_only`). Browser automation and LLM calls run on users' desktop clients; the cloud handles auth, orgs, workflows, scheduling, worker dispatch, and admin approval.

## Architecture

```
https://rpa.wenhandev.com
        │
        ▼
   Caddy (TLS, Let's Encrypt)
        │
        ▼
   FastAPI (uvicorn) + admin SPA
        │
        ▼
   SQLite volume (/app/data)
```

Desktop clients connect to `https://rpa.wenhandev.com` for login and worker WebSocket (`/api/v1/workers/connect`). Users download **Auto Agent Client** from `/client`.

## Prerequisites

1. VPS with Docker (Ubuntu 22.04+ recommended)
2. DNS **A record**: `rpa.wenhandev.com` → server public IP
3. Ports **80** and **443** open

## Quick start (on the server)

```bash
git clone <your-repo-url> /opt/auto-agent
cd /opt/auto-agent/deploy
cp .env.production.example .env
nano .env   # set SESSION_SECRET, ADMIN_PASSWORD
chmod +x bootstrap-server.sh entrypoint.sh
sudo ./bootstrap-server.sh
```

Or manually:

```bash
cd /opt/auto-agent/deploy
docker compose build
docker compose up -d
docker compose logs -f
```

Health check: `curl -fsS https://rpa.wenhandev.com/api/health`

## Environment variables

| Variable | Purpose |
|----------|---------|
| `EXECUTION_BACKEND` | Must be `control_plane_only` for cloud |
| `SESSION_SECRET` | Cookie/session signing (long random string) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Bootstrap admin account |
| `OAUTH_CALLBACK_BASE` | `https://rpa.wenhandev.com` |
| `FRONTEND_BASE_URL` | `https://rpa.wenhandev.com` |
| `CORS_ORIGINS` | Include production domain + local dev if needed |
| `DOMAIN` / `ACME_EMAIL` | Caddy TLS (compose env) |

## Admin workflow

1. Open `https://rpa.wenhandev.com` and sign in with admin credentials
2. **Settings → Workers** — approve client devices (`approval_required` is the default org policy)
3. Users install **Auto Agent Client** from `/client` and log in with the same cloud URL

## Client app (production)

Build with the cloud URL baked in:

```bash
cd client
VITE_CLOUD_URL=https://rpa.wenhandev.com npm run tauri build
```

Release builds must **not** spawn a local cloud on port 8001 (dev-only monolith behavior).

## Client downloads (free — same VM)

Installers are served at **`https://rpa.wenhandev.com/downloads/`** (Caddy static files on this VM; no extra cost).

| File | URL |
|------|-----|
| macOS | `/downloads/Auto-Agent-Client-macos.dmg` |
| Windows | `/downloads/Auto-Agent-Client-windows.msi` |
| Linux | `/downloads/Auto-Agent-Client-linux.AppImage` |

**Build & publish:**

1. Tag `client-v0.1.0` → GitHub Actions **Release client** builds installers.
2. Upload to VM (pick one):
   - **Automatic:** add repo secret `GCP_SA_KEY` (service account JSON with Compute OS Login / instance access). The workflow uploads after build.
   - **Manual:** download CI artifacts, then:
     ```bash
     chmod +x deploy/publish-client-downloads.sh
     ./deploy/publish-client-downloads.sh /path/to/release-assets
     ```
3. Redeploy app if you changed download URLs in `frontend/production.env.dist`.

Private GitHub Releases are **not** used for end-user downloads — only this VM path is public.

## Updates

```bash
cd /opt/auto-agent
git pull
cd deploy
docker compose build --pull
docker compose up -d
```

## Troubleshooting

| Issue | Check |
|-------|--------|
| Certificate pending | DNS propagated? Port 80 reachable from internet? |
| 502 Bad Gateway | `docker compose logs app` — uvicorn startup errors |
| Desktop login fails | Cloud URL exactly `https://rpa.wenhandev.com` (no trailing slash) |
| Worker stays pending | Admin must Approve in Settings → Workers |

Data persists in Docker volume `deploy_app_data` (SQLite + Fernet keys under `/app/data`).
