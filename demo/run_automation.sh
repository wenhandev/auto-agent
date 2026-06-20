#!/usr/bin/env bash
# Seed and run the Acme Supply Hub demo automation via POST /api/tasks.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="$ROOT/demo/seed_task.json"

# Prefer port 8000; fall back to 8765 if another app occupies 8000.
PORT="${AUTO_AGENT_PORT:-}"
if [ -z "$PORT" ]; then
  if curl -sf "http://127.0.0.1:8000/demo" -o /dev/null 2>/dev/null \
     && curl -sf -X POST "http://127.0.0.1:8000/api/tasks" \
          -H "Content-Type: application/json" -d '{"objective":"ping"}' \
          2>/dev/null | grep -qv '"detail":"Not Found"'; then
    PORT=8000
  elif curl -sf "http://127.0.0.1:8765/demo" -o /dev/null 2>/dev/null; then
    PORT=8765
  else
    echo "No auto_agent backend found. Start it first:" >&2
    echo "  cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload" >&2
    exit 1
  fi
fi

BASE="http://127.0.0.1:${PORT}"
echo "Using backend at $BASE"

python3 - "$SEED" "$BASE" <<'PY'
import json, sys, urllib.request

seed_path, base = sys.argv[1], sys.argv[2]
with open(seed_path) as f:
    payload = json.load(f)

demo_url = f"{base}/demo"
payload["start_url"] = demo_url
payload["objective"] = payload["objective"].replace(
    "http://localhost:8000/demo", demo_url
)

req = urllib.request.Request(
    f"{base}/api/tasks",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())

run_id = data["id"]
print(json.dumps(data, indent=2))
print()
print(f"Task created: {run_id}")
print(f"Poll status: curl -s {base}/api/tasks/{run_id} | jq .")
print(f"Watch in UI: http://localhost:5173 (frontend) — run {run_id}")
PY
