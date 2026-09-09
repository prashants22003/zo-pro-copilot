# Zo-Pro Copilot

Chat copilot over Wide World Importers sales and purchasing data. Ask in plain language, get answers from Postgres, open the underlying rows by splitting the chat — not a popup.

This repo is documentation-first. The running app is Docker Compose plus (for local chat) Ollama on the host.

## Read in this order

1. [`prd.md`](prd.md) — what we are building
2. [`design-guidelines.md`](design-guidelines.md) — visual system and extract-and-split
3. [`agentflow.md`](agentflow.md) — orchestrator and agents
4. [`docs/decisions.md`](docs/decisions.md) — locked choices
5. [`docs/architecture.md`](docs/architecture.md) — Compose, env, seed-if-empty
6. [`docs/data-setup.md`](docs/data-setup.md) — `.bak` → Postgres, demo clock
7. [`docs/data-readme.md`](docs/data-readme.md) — what you can ask, boundaries, example questions
8. Schema allow-lists: [`sales`](docs/schema-sales.md), [`purchasing`](docs/schema-purchasing.md), [`warehouse`](docs/schema-warehouse.md), [`application`](docs/schema-application.md)
9. [`docs/insight-rules.md`](docs/insight-rules.md) — advanced deterministic insights
10. [`docs/api.md`](docs/api.md) — HTTP/SSE
11. [`docs/evaluation.md`](docs/evaluation.md) — how to judge the demo (not a hardcoded script)

HTML under `mock ui/` is visual reference only. Tables in those files are popups; the MVP is the shrinking chat + data pane in the design guidelines.

## Data

Origin backup: `data/WideWorldImporters-Full.bak`

Phase 1 (once, CPU/RAM only, no GPU): `powershell -File infra/migrate/run.ps1` → `data/wwi-postgres.dump`

MVP Compose restores that dump if Postgres is empty; it does not start SQL Server.

## Demo clock

WWI dates are 2013–2016. Set “today” in the header (default example `2015-09-14`). The product ignores later rows and interprets “last quarter” / FY from that date. Fiscal year is the **calendar year** (so 14 Sep 2015 is FY2015 Q3). Asking which quarter or date you are on does not call the LLM.

## Run

1. Install [Ollama](https://ollama.com) on the host (not in Docker). Then:

   ```bash
   ollama pull qwen2.5-coder:7b-instruct-q4_K_M
   ```

   Leave Ollama running. The API container reaches it at `host.docker.internal:11434`. Domain agents use this model for SQL.

2. Copy `.env.example` to `.env`. Set `GEMINI_API_KEY`. Local chat uses **Gemini** as the orchestrator (`ORCH_PROVIDER=gemini`) and **Ollama coder** for Sales/Purchase SQL. Insight cards stay on templates (`INSIGHT_NARRATE=template`). Pytest and Vitest mock the LLMs and do not call Gemini.

3. `docker compose up --build`

4. Open http://localhost:8080

Clock/FY questions work even if Gemini and Ollama are down. Metric questions need Gemini (orchestrator) plus Ollama (SQL agents).

### Providers

```
ORCH_PROVIDER=gemini
ORCH_MODEL=gemini-3.6-flash
GEMINI_API_KEY=...
AGENT_PROVIDER=ollama
AGENT_MODEL=qwen2.5-coder:7b-instruct-q4_K_M
```

Do not set `AGENT_PROVIDER=gemini` — that puts the SQL retry loop on Gemini and will exhaust quota.

Postgres restores `data/wwi-postgres.dump` only when empty. SQL Server is not used.
