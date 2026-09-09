# API — Zo-Pro Copilot

FastAPI. JSON + SSE. No auth for MVP.

Clock: all data endpoints interpret “now” as `copilot.settings.demo_clock` unless overridden.

## `GET /health`

```json
{ "ok": true, "postgres": "ready", "seeded": true, "demo_clock": "2015-09-14" }
```

`seeded: false` → UI shows a waiting state; migrate should have blocked API start in Compose, so this is a safety net.

## `GET /clock`

```json
{ "demo_clock": "2015-09-14", "data_min": "2013-01-01", "data_max": "2016-05-31" }
```

`data_min` / `data_max` from `MIN/MAX(order_date)`: **2013-01-01** / **2016-05-31** on this dump.

## `PATCH /clock`

```json
{ "demo_clock": "2015-09-14" }
```

Persists, re-runs insight rules (async or inline if fast enough), returns the same shape as `GET /clock`. Reject dates with no data (optional warn if outside min/max).

## `GET /alerts`

Unresolved alerts for the current clock.

```json
{
  "alerts": [
    {
      "id": "uuid",
      "rule_id": "stockout_projection",
      "category": "warning",
      "text": "…",
      "metrics": {},
      "source_tables": ["warehouse.stock_item_transactions", "purchasing.purchase_orders"],
      "display_sources": ["Warehouse.StockItemTransactions", "Purchasing.PurchaseOrders"],
      "sql_executed": "SELECT …",
      "subject_key": "123",
      "created_at": "…",
      "as_of": "2015-09-14"
    }
  ]
}
```

## `POST /chat` — SSE

Body:

```json
{
  "message": "how did we perform last quarter?",
  "history": [{ "role": "user|assistant", "content": "…" }]
}
```

Clock-only messages (e.g. “which FY quarter are we in?”) use the same SSE contract (`token` + `done`) but never call an LLM.

MVP: server holds thread in memory per process or the client resends `history`. No DB transcripts.

SSE event types (`event:` field):

| event | data | Meaning |
|---|---|---|
| `token` | `{ "text": "…" }` | Assistant prose |
| `card` | insight or chart attachment | Render inline; click → drill-down |
| `sources` | `{ "display_sources": ["Sales.Invoices"] }` | Footer |
| `metrics_used` | `{ "metrics": ["trailing_90d_revenue", "prior_90d_revenue"] }` | Required for suggestions |
| `error` | `{ "message": "…" }` | Interface voice; end stream |
| `done` | `{ "message_id": "…" }` | End |

Card payload:

```json
{
  "id": "card-…",
  "kind": "insight | chart",
  "category": "warning | positive | info",
  "title": "Needs attention",
  "text": "…",
  "metrics": [{ "value": "6d", "label": "until stockout" }],
  "display_sources": ["Warehouse.StockItems"],
  "sql_executed": "SELECT …",
  "chart": {
    "type": "bar | hbar | line | pie",
    "labels": [],
    "values": [],
    "value_label": "invoiced value",
    "highlight_index": 3,
    "series": [{ "name": "optional second series", "values": [] }]
  }
}
```

## `POST /drilldown`

Opens or adds a data-pane tab. Reuses the SQL from the card. Server still enforces: SELECT only, allow-list of the **insight/cross** role (union), row cap, timeout, clock cutoff.

```json
{
  "sql_executed": "SELECT …",
  "title": "Stock and open purchase orders",
  "origin_card_id": "card-…",
  "subject_key": "optional entity name to highlight"
}
```

Response:

```json
{
  "tab_id": "tab-…",
  "title": "…",
  "breadcrumb": "Warehouse.StockItems filtered …",
  "sql_executed": "SELECT …",
  "columns": [{ "key": "stock_item_name", "label": "Stock item", "kind": "text | num" }],
  "rows": [[]],
  "flagged_row_indexes": [0],
  "kpis": [{ "value": "50", "label": "invoiced value" }],
  "chart": {
    "type": "bar | hbar | line | pie",
    "labels": ["A", "B"],
    "values": [10, 50],
    "value_label": "invoiced value",
    "highlight_index": 1
  }
}
```

`kpis` and `chart` are inferred on the server from the result set (dates → line, few positive shares → pie, long labels / many rows → horizontal bar, otherwise vertical bar). The model does not invent chart JSON. A single numeric row is KPIs only.

If the original SQL is an aggregate, drill-down may run a **detail variant** documented on the card (`detail_sql`). Prefer storing `detail_sql` on the card at generation time so the tab shows rows, not one summary line.

## Guardrails (every SQL endpoint)

- Parse and reject anything that is not a single `SELECT` (no WITH-to-DML, no multiple statements)
- Allow-list tables only
- `statement_timeout`, row cap
- Clock predicate required on dated tables (server may wrap in a subquery if missing — prefer reject-and-retry at the agent)

## CORS

`web` origin only in Compose. For a public demo, set `CORS_ORIGINS`.
