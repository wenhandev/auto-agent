# auto_agent Demo Script — Acme Supply Hub

Use this guide during client presentations to showcase **auto_agent** browser automation: login, navigation, forms, and structured data extraction.

## Prerequisites

1. Backend running on port 8000 (see [README.md](./README.md))
2. Portal open at http://localhost:8000/demo
3. For autonomous mode: configure `OPENAI_API_KEY` or `GOOGLE_API_KEY` in `backend/.env`

## Start commands

```bash
# Terminal 1 — backend
cd backend && uvicorn app.main:app --port 8000 --reload

# Terminal 2 — optional frontend UI for watching runs
cd frontend && npm run dev
```

Portal URL: **http://localhost:8000/demo**

Demo credentials: `demo@acme.com` / `demo1234` / OTP `123456`

---

## Copy-paste autonomous task objective

Use this in the auto_agent UI (**New Task**) or via API:

```
Log into the Acme Supply Hub supplier portal at http://localhost:8000/demo using email demo@acme.com, password demo1234, and OTP 123456. Navigate to Orders, search for order PO-2024-8842, click the row to open order details, and extract the order JSON including line items. Then go to Invoices, click Download Summary for invoice INV-2024-3325, and extract the invoice summary JSON. Finally open Support, submit a ticket: category "System Integration", subject "API webhook delay", description "EDI 856 acknowledgments are delayed by 2 hours since Nov 28". Return all extracted data.
```

### API equivalent

```bash
curl -s -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d @demo/seed_task.json | jq .
```

Poll status:

```bash
curl -s http://localhost:8000/api/tasks/<run_id> | jq .
```

---

## Step-by-step presentation narrative (5–8 min)

### Act 1 — Login & verification (90 sec)

> "Our agent handles real enterprise portals with multi-factor steps."

1. Agent navigates to `/demo`
2. Fills email `demo@acme.com` and password `demo1234`
3. Clicks Continue → OTP screen appears
4. Enters `123456` → lands on Dashboard

**Highlight:** Two-step auth flow, error handling if wrong OTP.

### Act 2 — Navigate & filter (60 sec)

> "The agent understands sidebar navigation and search forms."

1. Clicks **Orders / 采购订单** in sidebar
2. Types `8842` in order ID filter
3. Clicks **Search**
4. Clicks row **PO-2024-8842**

**Highlight:** Dynamic table filtering, row selection opens detail panel.

### Act 3 — Extract structured data (90 sec)

> "Beyond screenshots — we extract JSON-ready business data."

1. Reads order detail panel: buyer, status, line items
2. Extracts `#order-json` block (or uses `extract` tool on visible JSON)
3. Notes rush-order flag and SKU-level line items

**Sample extract target:**

```json
{
  "orderId": "PO-2024-8842",
  "buyer": "华东精密制造有限公司",
  "amount": 128450,
  "lineItems": [...]
}
```

### Act 4 — Shipments & Invoices (60 sec)

> "Expandable UI and action buttons — no problem."

1. Navigates to **Shipments**, expands **SHP-2024-4388**
2. Reads timeline events (warehouse pickup → hub arrival)
3. Navigates to **Invoices**, clicks **Download Summary** on **INV-2024-3325**
4. Extracts invoice JSON with tax breakdown

### Act 5 — Support ticket wizard (90 sec)

> "Multi-step forms with confirmation — fully automatable."

1. Navigates to **Support**
2. Step 1: selects category **System Integration / 系统对接**
3. Step 2: fills subject and description
4. Step 3: confirms and submits
5. Captures ticket ID and `#ticket-json` confirmation

**Highlight:** 3-step wizard, final structured ticket payload.

---

## Workflow-based alternative (deterministic)

For environments without LLM keys, build a workflow in the UI:

| Step | Node type | Params |
|------|-----------|--------|
| 1 | navigate | `url: http://localhost:8000/demo` |
| 2 | type_text | `#login-email` → `demo@acme.com` |
| 3 | type_text | `#login-password` → `demo1234` |
| 4 | click_element | `[data-testid=login-submit]` |
| 5 | type_text | `#otp-code` → `123456` |
| 6 | click_element | `[data-testid=otp-submit]` |
| 7 | click_element | `[data-testid=nav-orders]` |
| 8 | type_text | `#filter-order-id` → `8842` |
| 9 | click_element | `[data-testid=filter-submit]` |
| 10 | click_element | `[data-testid=order-row-PO-2024-8842]` |
| 11 | extract | target: `#order-json` |

Use `data-testid` selectors for stability across EN/ZH language toggles.

---

## UI patterns designed for automation

| Pattern | Location | `data-testid` |
|---------|----------|---------------|
| Login form | Login step 1 | `login-email`, `login-password`, `login-submit` |
| OTP form | Login step 2 | `otp-code`, `otp-submit` |
| Sidebar nav | All pages | `nav-dashboard`, `nav-orders`, `nav-shipments`, `nav-invoices`, `nav-support` |
| Order filter | Orders | `filter-order-id`, `filter-status`, `filter-submit` |
| Order rows | Orders table | `order-row-PO-2024-8842` (per order) |
| Order JSON | Detail panel | `order-json` |
| Shipment expand | Shipments | `shipment-toggle-SHP-2024-4388` |
| Invoice download | Invoices | `download-summary-INV-2024-3325` |
| Invoice JSON | Summary panel | `invoice-json` |
| Support wizard | Support | `ticket-category`, `support-next-1`, `ticket-subject`, `ticket-description`, `support-submit` |
| Ticket JSON | Success | `ticket-json` |
| Role button | Orders (rush) | `approve-rush-btn` (visible for PO-2024-8842) |

---

## Smoke verification

```bash
# Static file + redirect tests
cd backend && pytest tests/test_demo_portal.py -v

# Manual Playwright smoke (requires running backend)
python scripts/run_demo_portal_smoke.py
```

Expected smoke output: login succeeds, orders page loads, order detail JSON present.
