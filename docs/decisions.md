# Decisions — Zo-Pro Copilot

Locked before implementation. Change here if we change our minds.

## Product

- **Name:** Zo-Pro Copilot. Mockups may still say “Current”; the app does not.
- **Audience:** demo / assignment prototype, not production multi-tenant SaaS.
- **Auth:** none. Single conversation, desktop, 1440px.
- **Questions:** never hardcoded. Agents generate SQL against allow-lists.
- **Deadline stated by owner:** 9 August, morning. Workspace calendar at doc time was 6 September 2026 — **confirm** whether the real hand-in is 9 August or 9 September.

## Design

- HTML mocks = color, type, card anatomy only.
- **No popup / drawer / scrim** for tables.
- Click card → chat shrinks left, **fragment of the card extracts** and morphs into the data pane; origin card stays highlighted in the thread.
- Multiple dashboards = **tabs** in the data pane.
- Chat remains usable while data is open.
- Extract-and-split is the primary motion of the product (`design-guidelines.md` §5).

## Data

- Source: `data/WideWorldImporters-Full.bak` (SQL Server OLTP Full, ~121 MB).
- Runtime DB: **PostgreSQL**. Everyday seed is `data/wwi-postgres.dump`. SQL Server is **phase 1 only** (`infra/migrate`), not MVP Compose.
- Phase 1 containers: no GPU, SQL Server `MSSQL_MEMORY_LIMIT_MB=2048`. This workload does not use the RTX 3050.
- CSVs in `data/unused/` are unused.
- Physical identifiers: `snake_case` Postgres. UI citations: `Sales.Orders` style display names.
- Agents get **allow-lists**, not the whole WWI catalog. Orchestrator has the routing catalog (`agentflow.md` §5).
- **Demo clock** with inclusive cutoff: ignore dates **after** the clock. Default example: `2015-09-14`. Adjustable in the header.
- **Fiscal year = calendar year** (Q1 Jan–Mar). Clock-only questions (date / FY / quarter / month) are answered from the clock with no LLM.
- Stock as of clock: **end-of-data holdings minus movements after the clock** (see `docs/schema-warehouse.md`). Transaction `quantity` is signed (issues negative).

## Agents

- Hub-and-spoke: Orchestrator, Sales, Purchase, Insight.
- Insight = advanced deterministic catalog (`docs/insight-rules.md`); card text is the rule template unless `INSIGHT_NARRATE=llm`.
- Cross-schema SQL only via `cross_domain_query` / insight role.
- **LLM:** Orchestrator is Gemini Flash (`ORCH_PROVIDER=gemini`, `gemini-3.6-flash`). Sales/Purchase agents are Ollama coder (`AGENT_PROVIDER=ollama`). Tests mock providers and never call Gemini. No Groq/OpenRouter in this pass.

## Infra

- `docker compose up` (MVP): if Postgres healthy and **empty**, restore `wwi-postgres.dump`; if already seeded, skip.
- Optional later: same stack behind a demo URL.

## Open until after first seed

- Exact `data_min` / `data_max` on orders — **locked:** `2013-01-01` → `2016-05-31`
- Sign of `stock_item_transactions.quantity` — **locked:** issues negative, receipts positive; holdings ≠ sum of all txns
- Which insight rules actually fire at the locked clock (then record here)
- Whether `on_time_supplier` is viable given receipt dates
