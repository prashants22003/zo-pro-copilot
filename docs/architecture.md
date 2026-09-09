# Architecture — Zo-Pro Copilot

Runtime shape of the MVP. Product behavior lives in `prd.md`, `agentflow.md`, and `design-guidelines.md`.

## 1. Services

One Compose project. Typical developer and demo command: `docker compose up --build`.

| Service | Image / build | Role |
|---|---|---|
| `postgres` | `postgres:16` | App database. |
| `api` | FastAPI app | Orchestrator, agents, SSE, drill-down, clock, alerts. |
| `web` | Vite/React (or nginx) | UI. |

**Phase 1 (once):** `infra/migrate` restores `data/WideWorldImporters-Full.bak` in SQL Server (RAM-capped, **no GPU**), copies the allow-list into Postgres, then writes `data/wwi-postgres.dump`. SQL Server is not part of the MVP stack.

**MVP compose:** start Postgres; if empty, `pg_restore` the dump; if `sales.orders` has rows, skip. Never start SQL Server at app boot.

## 2. Request path

```
browser  --SSE /chat-->  FastAPI
                           ├─ clock-only shortcut (no LLM)
                           ├─ orchestrator → Gemini Flash (route + synthesize)
                           ├─ sales / purchase agents → host Ollama coder + execute_sql
                           ├─ sales_agent_role     --> postgres
                           ├─ purchase_agent_role  --> postgres
                           ├─ insight / cross role --> postgres
                           └─ copilot.alerts, copilot.settings (clock)
```

No LangChain/LangGraph. Direct provider HTTP/SDK + tool definitions from `agentflow.md`. Orchestrator and domain agents may use different providers.

## 3. Environment

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | App owner / migrate (DDL). Not used by agents. |
| `SALES_DATABASE_URL` | `sales_agent_role` |
| `PURCHASE_DATABASE_URL` | `purchase_agent_role` |
| `INSIGHT_DATABASE_URL` | Insight + `cross_domain_query` (union allow-list, read; insight may write `copilot.alerts`) |
| `GEMINI_API_KEY` | Required for the orchestrator (`ORCH_PROVIDER=gemini`) |
| `ORCH_PROVIDER` | Default `gemini` — user-facing router |
| `ORCH_MODEL` | Default `gemini-3.6-flash` |
| `AGENT_PROVIDER` | Default `ollama` — Sales/Purchase SQL |
| `AGENT_MODEL` | Default `qwen2.5-coder:7b-instruct-q4_K_M` |
| `LLM_PROVIDER` / `LLM_MODEL` | Legacy fallback; do not point domain agents at Gemini |
| `OLLAMA_HOST` | Default `http://host.docker.internal:11434`. Ollama runs on the **host**, not in Compose |
| `INSIGHT_NARRATE` | `template` (default) or `llm` |
| `DEMO_CLOCK` | Default as-of date, `YYYY-MM-DD` (e.g. `2015-09-14`) |
| `QUERY_TIMEOUT_MS` | Default 5000 |
| `QUERY_ROW_CAP` | Default 500 |
| `WWI_DUMP_PATH` | `data/wwi-postgres.dump` (everyday seed). The `.bak` is phase-1 only. |

Never commit keys. `.env` is local. The `.bak` stays in `data/` and is not committed (see `.gitignore`).

## 4. LLM

Local demo: **Gemini Flash** is the orchestrator (client-facing; assigns `sales_agent` / `purchase_agent` / `get_live_alerts`). **Ollama** `qwen2.5-coder:7b-instruct-q4_K_M` is the domain SQL loop. Pull the coder model once (`ollama pull qwen2.5-coder:7b-instruct-q4_K_M`). The API container calls `OLLAMA_HOST`.

Orchestrator default is `gemini-3.6-flash`. Tests mock `generate` and never call Gemini.

Clock-only questions never call a provider. Insight cards use templates unless `INSIGHT_NARRATE=llm` (leave that off).

The orchestrator prompt is the routing catalog plus metric contract. Domain agents load schema markdown (allow-list files) plus clock windows.

## 5. Frontend

- React + Vite + Tailwind tokens from `design-guidelines.md` + Framer Motion
- Chat column is a dynamic box: rest = centered 760px; split = left ~460px
- Extract-and-split is the main motion; tabs in the data pane (KPIs + live chart inferred from SQL rows + table)
- Demo clock in the header; `PATCH /clock` then refetch alerts
- SSE for assistant tokens and structured attachments (cards, charts)

Designed at 1440px. A public demo link should be opened at desktop width.

## 6. Deploy (optional)

Same Compose stack on a VM or a host that can run Docker. Expose `web` (and API if not proxied). Set `ORCH_PROVIDER=gemini`, `GEMINI_API_KEY`, and keep `AGENT_PROVIDER=ollama` if the host can reach Ollama; otherwise metric questions need a reachable coder model.

## 7. What “healthy and empty → seed” means (MVP)

1. Start `postgres`. Wait until accepting connections.
2. If `sales.orders` exists and `COUNT(*) > 0` → skip.
3. Else `pg_restore` `data/wwi-postgres.dump`, then apply `infra/migrate/roles.sql` if roles were not in the dump.
4. Start `api`, then `web`.

Re-seed: drop the Postgres volume and restore the dump again. To rebuild the dump from Microsoft’s `.bak`, run `infra/migrate/run.ps1` (slow, SQL Server, CPU/RAM only).
