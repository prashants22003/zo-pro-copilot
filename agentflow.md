# Agent flow — Zo-Pro Copilot

How the orchestrator and the three agents (Sales, Purchase, Insight) are structured, how they communicate, what each is allowed to query, and how unscripted questions move through the system.

Questions are **not hardcoded**. Example utterances below are routing illustrations only.

## 1. Topology

Hub-and-spoke. The orchestrator is the only component that talks to the user and the only component that talks to more than one agent. Agents never call each other.

```
                    ┌─────────────┐
      user  ───────►│ Orchestrator │
                     └──────┬──────┘
             ┌──────────────┼──────────────┐
             ▼               ▼               ▼
      ┌────────────┐  ┌────────────┐  ┌───────────────┐
      │ Sales agent │  │Purchase agent│  │ Insight agent │
      └──────┬─────┘  └──────┬─────┘  └───────┬───────┘
             │               │                 │
      allow-list       allow-list         both allow-lists
      sales_agent_role purchase_agent_role  + writes copilot.alerts
```

Cross-domain work is combining two result sets (or one exceptional cross-schema SELECT), not a negotiation between agents. Every “who answers this” decision is visible in one trace.

## 2. Demo clock (all agents)

Every query and every insight rule is evaluated **as of** `copilot.demo_clock` (see `docs/data-setup.md`).

- Inclusive cutoff: rows with a transaction/order/invoice date **after** the clock are ignored.
- Relative language (“last month”, “this quarter”, “this FY”, “yesterday”) resolves against the clock, not the OS date. Fiscal year is the calendar year.
- The clock is passed into every agent call as ISO date `YYYY-MM-DD`.
- Agents must apply the cutoff on the correct date column (documented per table in the schema files). Missing the cutoff is a bug, not a style issue.

Stock on hand as of the clock is **not** raw `warehouse.stock_item_holdings` unless the clock equals data-end (2016-05-31). Use holdings minus movements **after** the clock (`docs/schema-warehouse.md`).

## 3. Components

### 3.1 Orchestrator

Owns the conversation. Does not guess numbers.

Responsibilities:

- Receive user message, thread history, demo clock, and which data-pane tabs are open
- **Clock-only shortcut:** if the turn only asks the date / FY / quarter / month as of the demo clock, answer from `windows()` and do not call an LLM
- Classify remaining intent using the **routing catalog** (§5): Sales, Purchase, both, insight-only, or out of scope
- Call the relevant agent(s) with a rewritten sub-question plus context (clock, subject, open tab)
- For cross-domain questions, reason over both `AgentResult`s; use `cross_domain_query` only when a real SQL join is required
- Stream the final answer; attach `source_tables`, `sql_executed` list, and optional chart spec so the UI can render cards
- On session start (and when the clock changes): `get_live_alerts()` and surface insight cards
- For “what next quarter looks like”: require trailing metrics from agents, then narrate a **suggestion** that names those metrics. Never claim a model forecast

The orchestrator does **not** run user-driven SQL against `sales.*` or `purchasing.*` in the normal path. It delegates so privilege stays in the DB role. It may use a broader read-only role only for `cross_domain_query` (§4.3).

It **does** hold a full map of allow-lists and “where to look” so it can assign work and ask agents for the right slice. That map is this file plus the schema docs. It is not a second copy of every column.

Tools:

```
sales_agent(question: str) -> AgentResult
purchase_agent(question: str) -> AgentResult
get_live_alerts() -> list[Alert]
cross_domain_query(query: str) -> QueryResult
```

The user-facing model is the **orchestrator** (Gemini Flash locally). It assigns work; it does **not** write SQL. Sales and Purchase agents (Ollama coder) call `execute_sql` under `sales_agent_role` / `purchase_agent_role`. `cross_domain_query` is the insight role when a statement must touch both sales-specific and purchasing-specific tables. The orchestrator never narrates “I will ask the sales agent” to the user.

Tests mock `generate` and never call Gemini or Ollama. Cap: two orchestrator LLM calls per turn (route, then synthesize). Domain agents keep their own SQL loop.

`AgentResult` from a completed SQL call:

```json
{
  "answer": "natural-language summary from the sub-agent",
  "rows": [],
  "sql_executed": ["SELECT ..."],
  "source_tables": ["sales.orders", "sales.customers"],
  "display_sources": ["Sales.Orders", "Sales.Customers"],
  "chart": null,
  "confidence": "ok | partial | no_data",
  "metrics_used": ["trailing_3m_revenue", "prior_3m_revenue"]
}
```

`metrics_used` is required when the user asked for a projection or “how did we perform” summary so the orchestrator can disclose methodology.

### 3.2 Sales agent

- Role: `sales_agent_role`, `SELECT` only
- Allow-list: `docs/schema-sales.md` plus read on `warehouse.stock_items` (product names) and `application` geography/people as listed there
- Input: routed question, schema context, clock, conversation context
- Loop: generate SQL → execute → inspect → optional follow-up SQL → one `AgentResult`
- Tool: `execute_sql(query)` — reject non-SELECT, row cap 500, timeout 5s, injector prepends clock cutoff if the agent omitted it (fail closed: reject queries with no recognizable date predicate on a dated table)

### 3.3 Purchase agent

Mirror of Sales. Role `purchase_agent_role`. Allow-list in `docs/schema-purchasing.md` plus `warehouse.stock_items`, `warehouse.stock_item_holdings` (metadata only; on-hand as of clock from transactions), `warehouse.stock_item_transactions`.

Same `execute_sql` guardrails.

### 3.4 Insight agent

Does not answer chat turns. Runs on session start, on clock change, and optionally on a simple interval.

Two layers, never mixed:

1. **Rule layer** (SQL/Python, no LLM): the catalog in `docs/insight-rules.md`. A rule fires or it does not.
2. **Narration layer**: by default the rule **template** is stored as card text (`INSIGHT_NARRATE=template`). Optional LLM narration (`INSIGHT_NARRATE=llm`) only rewrites rows a rule already flagged. It does not decide what is concerning.

Writes `copilot.alerts` (see `docs/api.md`). Orchestrator only reads unresolved rows for the current clock.

## 4. Routing logic

### 4.0 Clock-only (no LLM)

The question is only asking what “today” is on the demo clock, or which calendar month / quarter / fiscal year that implies.

- Fiscal year **is the calendar year**. Q1 = Jan–Mar. On `2015-09-14` that is **FY2015 Q3** (1 Jul–14 Sep as “this quarter”).
- Answer from `clock.windows()` with no tool calls and no SQL.
- Fail closed: any performance language (“how did”, revenue, sales, invoices, stock, …) goes to §4.1+.
- “How did last quarter look?” is **not** clock-only.

### 4.1 Single-domain

The question is answerable from one allow-list (top customers, revenue by month, supplier lead time, overdue POs). Call that agent. Light rephrase for continuity. Done.

### 4.2 Ambiguous but single-domain

No schema named, but one domain is enough (“what’s selling well” → Sales). Infer and proceed. Do not ask a clarifying question for this case.

### 4.3 Cross-domain

Needs both (margin, buying vs selling, slow suppliers on best sellers, next-period suggestion that uses sales *and* cost).

1. Call **both** agents in parallel with split sub-questions.
2. Join in orchestrator reasoning when keys line up (`stock_item_id`, month, region).
3. If a real join is required (`sales.order_lines` ⋈ `purchasing.purchase_order_lines` on `stock_item_id` with filters neither side can express), use `cross_domain_query`. Exception, not default.
4. `cross_domain_query` is read-only, allow-listed to the **union** of both agents’ tables, still clock-filtered. Reject writes and unknown tables.

### 4.4 Out of scope

Not in the data (HR policy, “write a poem”, schema we did not migrate). Answer without an agent and say the answer is **not** grounded in company tables.

### 4.5 Projection / “expected to perform”

Always:

1. Pull trailing metrics (and same period last year if the clock allows).
2. Compute a simple suggestion (run-rate or seasonal-naive — `docs/insight-rules.md` §Projection helper).
3. State it as a suggestion and list `metrics_used`.

Never a freeform LLM guess with no query.

## 5. Routing catalog (orchestrator “where to look”)

This is how the orchestrator assigns work. Agents get the matching schema file with a shorter “look here first” section.

| Intent (examples, not a menu) | Route | Look first |
|---|---|---|
| What date / today / as of / which FY or quarter / what month | Clock-only (§4.0), no LLM | `copilot.settings.demo_clock` via `clock.windows()` |
| Money in, revenue, profit on sales, invoices, “how did we perform”, monthly earnings | Sales | `sales.invoices`, `sales.invoice_lines` (earned); `sales.orders` / `order_lines` (booked) |
| Customers, who bought, who went quiet, top accounts | Sales | `sales.customers`, `sales.orders`, `sales.invoices` |
| Region / country / state growth or loss | Sales | `sales.customers.delivery_city_id` → `application.cities` → `state_provinces` → `countries`; facts from invoices/orders |
| Products selling, mix, units | Sales | `sales.order_lines` / `invoice_lines` + `warehouse.stock_items` |
| Salespeople | Sales | `sales.orders.salesperson_person_id` → `application.people` |
| Money out, PO cost, suppliers, lead time, overdue receipts | Purchase | `purchasing.purchase_orders`, `purchase_order_lines`, `suppliers` |
| Stock on hand, reorder, stockout, inbound vs demand | Purchase (+ Sales if demand) | transactions as of clock; `stock_items`; POs not yet received |
| Margin, buy vs sell, cost vs price | Both, then join or `cross_domain_query` | sale: invoice/order unit price; cost: PO `expected_unit_price_per_outer` / `quantity_per_outer` or last cost on transactions |
| Next month/quarter suggestion | Both, then orchestrator | trailing 3 months vs prior 3; same quarter last year if clock ≥ 1 year into data |
| “What’s wrong / what needs attention” | Insights already in `copilot.alerts`; do not invent new rules mid-turn | `get_live_alerts` |

If a question spans two rows, use §4.3.

## 6. End-to-end examples

These are traces, not product scripts.

### 0 — clock only

1. User: “which FY quarter are we in?”
2. Orchestrator answers from `windows()` — no LLM, no SQL
3. On `2015-09-14`: FY2015 Q3 (1 Jul 2015 through the clock)

### A — single domain

1. User: “which customers had the biggest drop in orders this month?”
2. Orchestrator → `sales_agent` with clock-defined “this month”
3. Sales agent compares order counts/value this month vs previous month
4. Returns `display_sources: ["Sales.Orders", "Sales.Customers"]`
5. Orchestrator streams the answer; UI may attach a chart card the user can open as a tab

### B — insight then split-chat

1. Session start → `get_live_alerts()`
2. Stockout rule fired for a SKU
3. Insight card in the thread (ember, sources, SQL attached)
4. User clicks the card → frontend extract-and-split; `POST /drilldown` reuses `sql_executed` with pagination
5. Follow-up: “did we undersize the reorder?” → orchestrator keeps product context → `purchase_agent`

### C — cross-domain

1. User: “which products have the thinnest margin right now?”
2. Both agents in parallel (avg selling price vs avg inbound cost per `stock_item_id`)
3. Orchestrator joins on `stock_item_id`; if messy, `cross_domain_query`
4. Answer cites both display sources; card opens a tab

### D — unscripted performance + suggestion

1. User: “how did we perform last quarter, and how should we think about the next one?”
2. Sales: last-quarter revenue, units, region mix vs prior quarter
3. Purchase: last-quarter spend, overdue POs, cost movement
4. Orchestrator synthesizes performance, then a next-quarter **suggestion** with `metrics_used` listed in the message

## 7. Error handling

- `execute_sql` fails (syntax, timeout, empty): agent gets **one** retry with the error text, then `confidence: "no_data"`
- Orchestrator tells the user what could not be determined; it does not invent a number
- `cross_domain_query` touching a non-allow-listed table or any write: reject before execution
- Clock change invalidates open-tab SQL that used the old cutoff; UI should refetch or close tabs with a quiet notice

## 8. Access matrix

Physical names are Postgres (`sales.orders`). UI shows display names (`Sales.Orders`).

| | Sales agent | Purchase agent | Orchestrator | Insight agent |
|---|---|---|---|---|
| Sales allow-list | read | — | via `sales_agent` | read (rules only) |
| Purchasing allow-list | — | read | via `purchase_agent` | read (rules only) |
| `warehouse.stock_items` | read | read | via either | read |
| `warehouse.stock_item_transactions` | — | read | via purchase or cross | read |
| `application.cities` / states / countries | read (region) | read (supplier city) | via agents or cross | read |
| `application.people` | read (salesperson) | read (PO contact) | via agents | — |
| `copilot.alerts` | — | — | read | write |
| User-driven SQL | own allow-list | own allow-list | `cross_domain_query` only | rules only |

Exact table lists: schema docs. Do not `GRANT SELECT` on `website`, `sequences`, or unmigrated WWI objects.
