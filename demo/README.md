# Acme Supply Hub — Client Demo Portal

B2B supplier portal demo for **auto_agent** sales presentations and browser automation showcases.

## Demo credentials

| Field | Value |
|-------|-------|
| Email | `demo@acme.com` |
| Password | `demo1234` |
| Step 2 | Google reCAPTCHA v2 (test keys — always passes) |

Uses Google reCAPTCHA test site keys; verification goes through `/api/test/recaptcha-verify`.

## Quick start

### 1. Start the backend

```bash
cd backend
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
uvicorn app.main:app --port 8000 --reload
```

### 2. Open the portal

| URL | Description |
|-----|-------------|
| http://localhost:8000/demo | Short redirect to portal |
| http://localhost:8000/static/portal/index.html | Direct portal URL |

### 3. Walk through the demo

1. **Login** — enter credentials, complete reCAPTCHA, click Verify
2. **Dashboard** — KPI cards and recent orders table
3. **Orders** — filter form, click a row for line-item detail + JSON extract panel
4. **Shipments** — expand cards to reveal tracking timeline events
5. **Invoices** — click "Download Summary" to reveal structured invoice JSON
6. **Support** — 3-step ticket wizard with confirmation JSON

## What makes this good for auto_agent

- **Multi-step login** (credentials + reCAPTCHA) — tests form filling, CAPTCHA click, and step transitions
- **Navigation** — sidebar with 5 sections, role-based "Approve Rush" button
- **Dynamic tables** — filter/search, row selection, detail panel update
- **Data extraction** — JSON blocks with `data-testid` targets (`order-json`, `invoice-json`, `ticket-json`)
- **Expand/collapse** — shipment timeline toggles
- **Multi-step wizard** — support ticket form (category → details → confirm)
- **Bilingual UI** — EN/中文 toggle for China client demos
- **Stable selectors** — `data-testid` on all key interactive elements

## File layout

```
backend/static/portal/
  index.html    # SPA shell
  styles.css    # Professional B2B styling
  app.js        # Mock data, routing, i18n

demo/
  README.md           # This file
  auto_agent_demo.md  # Copy-paste task objectives & workflow narrative
  seed_task.json      # Autonomous task spec for POST /api/tasks
```

## Seed and run automation

### Autonomous task (LLM-driven)

Requires `GOOGLE_API_KEY` or Vertex config in `backend/.env`. Auto-detects backend port (8000 or 8765):

```bash
./demo/run_automation.sh
```

Poll status:

```bash
curl -s http://localhost:8765/api/tasks/<run_id> | jq .
```

### Deterministic workflow (recommended for live demos)

No LLM required for navigation — uses `data-testid` selectors end-to-end:

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload   # or 8765 if 8000 is busy
cd backend && .venv/bin/python3 ../demo/seed_demo_workflow.py
```

Poll status:

```bash
curl -s http://localhost:8765/api/runs/<run_id> | jq .run.status
```

Workflow spec: `demo/seed_workflow.json` · Autonomous spec: `demo/seed_task.json`

## Optional: run smoke script

With backend on port 8000:

```bash
python scripts/run_demo_portal_smoke.py
```

Or run the pytest suite:

```bash
cd backend && pytest tests/test_demo_portal.py -v
```

## Screenshots (key pages)

1. **Login** — teal gradient background, two-step indicator, Acme branding
2. **Dashboard** — 4 KPI cards, recent orders table with status badges
3. **Orders** — split view: filterable table + order detail with line items and JSON extract
4. **Shipments** — expandable cards with dot timeline (done/pending states)
5. **Invoices** — table with download button revealing tax breakdown + JSON
6. **Support** — 3-step wizard ending in ticket ID + structured JSON confirmation
