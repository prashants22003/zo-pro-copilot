# Zo-Pro Copilot

Chat copilot over Wide World Importers sales and purchasing data. Ask in plain language, get answers from Postgres, open the underlying rows by splitting the chat — not a popup.

This repo is documentation-first. Chat uses **Gemini** (orchestrator) and **NVIDIA NIM** (SQL agents) against **Supabase Postgres**. The same keys and database work on your laptop and on Render.

## Read in this order

1. [`prd.md`](prd.md) — what we are building
2. [`design-guidelines.md`](design-guidelines.md) — visual system and extract-and-split
3. [`agentflow.md`](agentflow.md) — orchestrator and agents
4. [`docs/decisions.md`](docs/decisions.md) — locked choices
5. [`infra/architecture.md`](infra/architecture.md) — NIM, Supabase, Render, Vercel
6. [`docs/architecture.md`](docs/architecture.md) — Compose internals, env names, seed-if-empty
7. [`docs/data-setup.md`](docs/data-setup.md) — `.bak` → Postgres, demo clock
8. [`docs/data-readme.md`](docs/data-readme.md) — what you can ask, boundaries, example questions
9. Schema allow-lists: [`sales`](docs/schema-sales.md), [`purchasing`](docs/schema-purchasing.md), [`warehouse`](docs/schema-warehouse.md), [`application`](docs/schema-application.md)
10. [`docs/insight-rules.md`](docs/insight-rules.md) — advanced deterministic insights
11. [`docs/api.md`](docs/api.md) — HTTP/SSE
12. [`docs/evaluation.md`](docs/evaluation.md) — how to judge the demo (not a hardcoded script)

HTML under `mock ui/` is visual reference only. Tables in those files are popups; the MVP is the shrinking chat + data pane in the design guidelines.

## Data

Origin backup: `data/WideWorldImporters-Full.bak`

Phase 1 (once, CPU/RAM only, no GPU): `powershell -File infra/migrate/run.ps1` → `data/wwi-postgres.dump`

MVP Compose can still restore that dump with `--profile local-db` if Postgres is empty. The default path is a hosted Supabase database (see [`infra/architecture.md`](infra/architecture.md)). SQL Server is not used at runtime.

## Demo clock

WWI dates are 2013–2016. Set “today” in the header (default example `2015-09-14`). The product ignores later rows and interprets “last quarter” / FY from that date. Fiscal year is the **calendar year** (so 14 Sep 2015 is FY2015 Q3). Asking which quarter or date you are on does not call the LLM.

## Run

1. Copy `.env.example` to `.env`. Set `GEMINI_API_KEY` and `NVIDIA_API_KEY`. Point the four `*_DATABASE_URL` values at your Supabase **session pooler** (port 5432) with `sslmode=require`.

2. Start the API (uses Supabase + NIM, no local Postgres):

   ```bash
   docker compose up --build api
   ```

   Frontend: `cd frontend && npm run dev` → http://localhost:5173  
   Or also start Compose `web` → http://localhost:8080

3. Optional offline stack (Ollama + Compose Postgres): set `AGENT_PROVIDER=ollama` and run `docker compose --profile local-db up --build`.

Insight cards stay on templates (`INSIGHT_NARRATE=template`). Pytest and Vitest mock the LLMs and do not call Gemini or NIM.

Clock/FY questions work even if Gemini and NIM are down. Metric questions need both keys plus a seeded database.

### Providers

```
ORCH_PROVIDER=gemini
ORCH_MODEL=gemini-3.6-flash
GEMINI_API_KEY=...
AGENT_PROVIDER=nvidia
AGENT_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NVIDIA_API_KEY=...
```

Do not set `AGENT_PROVIDER=gemini` — that puts the SQL retry loop on Gemini and will exhaust quota.

Postgres dump restore (local-db profile or one-time Supabase seed) uses `pg_restore` on `data/wwi-postgres.dump`. SQL Server is not used.
