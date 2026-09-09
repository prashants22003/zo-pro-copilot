# Architecture — Zo-Pro Copilot

Laptop and the public demo are the **same mode**: Gemini (orchestrator) + NVIDIA NIM (SQL agents) + one Supabase Postgres. Ollama remains in the codebase as an optional local path; it is not the default. There is no Groq fallback.

## 1. One running mode

```
┌──────────────┐     HTTPS      ┌─────────────────────┐
│ Vercel        │───────────────►│ Render (FastAPI)     │
│ (static UI)   │               │ or laptop uvicorn    │
└──────────────┘               └──────────┬──────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
           ┌────────────────┐    ┌──────────────┐    ┌──────────────────┐
           │ Supabase        │    │ Gemini API    │    │ NVIDIA NIM        │
           │ Postgres        │    │ orchestrator  │    │ nvidia/nemotron-  │
           │ (session pooler,│    │ gemini-3.6-   │    │ 3.5-lightning-    │
           │  sslmode=require)│    │ flash         │    │ 30b-a3b            │
           └────────────────┘    └──────────────┘    └──────────────────┘
```

The laptop uses the same four DB URLs, `GEMINI_API_KEY`, and `NVIDIA_API_KEY` as Render. Switching to a public URL is hosting, not a code fork.

| | Laptop | Shared demo |
|---|---|---|
| Frontend | Vite (`npm run dev`) or Compose `web` | Vercel static build |
| Backend | uvicorn or Compose `api` | Render free web service (Docker) |
| Database | Supabase | Same Supabase project |
| Orchestrator | Gemini Flash `gemini-3.6-flash` | Same |
| Agent LLM | NVIDIA NIM `nvidia/nemotron-3.5-lightning-30b-a3b` | Same |
| Optional offline DB | `docker compose --profile local-db up` | not used |

## 2. Local development

```bash
cp .env.example .env   # keys + Supabase session-pooler URLs
docker compose up --build api
# or: uvicorn from backend/ with PYTHONPATH, plus npm run dev in frontend/
```

Open http://localhost:5173 (Vite, proxies `/api` → `:8000`) or http://localhost:8080 (Compose `web`).

Optional fully-local Postgres (no Supabase):

```bash
docker compose --profile local-db up --build
```

Set the four `*_DATABASE_URL` values to the Compose Postgres roles in that case. Dump restore still uses `pg_restore` via `infra/seed/seed.sh`.

## 3. Shared demo hosting ($0)

- **Frontend**: Vercel. Root `frontend/`, `npm run build`. Set build-time `VITE_API_BASE_URL=https://<api>.onrender.com`. Public URL like `zo-pro-copilot.vercel.app`.
- **Backend**: Render free Docker web service from [backend/Dockerfile](../backend/Dockerfile). Port `$PORT` (defaults to 8000). Health check `GET /health`. Free instances sleep after ~15 minutes idle; the next request can take 30–60s.
- Browser calls Render **directly**. Do not rewrite `/chat` through Vercel (SSE + Hobby limits).
- `CORS_ORIGINS` on Render must include the Vercel origin.

### 3.1 Database (Supabase)

Hosted Postgres only — not a container you manage. Free tier is **500 MB**; measure local size first:

```sql
SELECT pg_size_pretty(pg_database_size('zopro'));
```

If that is over ~400 MB, trim before restore. Do not add a credit card.

Restore is **`pg_restore`**, not `psql < dump`. The file is `pg_dump -Fc`:

```bash
pg_restore --no-owner --no-acl -d "$SUPABASE_SESSION_URI" data/wwi-postgres.dump
psql "$SUPABASE_SESSION_URI" -f infra/migrate/roles.sql
psql "$SUPABASE_SESSION_URI" -f infra/seed/after_restore.sql
```

Use the **session pooler** (port **5432**), not transaction pooler 6543. The API issues `SET statement_timeout` per connection. Append `?sslmode=require`.

Create the same least-privilege roles (`sales_agent_role`, `purchase_agent_role`, `insight_role`) with **new** passwords — do not reuse `sales_agent_local` on a public host. Point:

```
DATABASE_URL=postgresql://postgres.PROJECT:...@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
SALES_DATABASE_URL=postgresql://sales_agent_role:...@...pooler.supabase.com:5432/postgres?sslmode=require
PURCHASE_DATABASE_URL=...
INSIGHT_DATABASE_URL=...
```

Free projects pause after **7 days idle**; unpause in the dashboard. Do not use Supabase Auth, JS client, or PostgREST.

## 4. Provider config surface

```
ORCH_PROVIDER=gemini
ORCH_MODEL=gemini-3.6-flash
GEMINI_API_KEY=...

AGENT_PROVIDER=nvidia
AGENT_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NVIDIA_API_KEY=nvapi-...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

INSIGHT_NARRATE=template
```

`generate()` in `backend/app/llm.py` branches `gemini` | `nvidia` | `ollama`. NIM uses the OpenAI-compatible client in `backend/app/providers/openai_compat.py`. Optional local Ollama: `AGENT_PROVIDER=ollama` and `OLLAMA_HOST`.

Do not set `AGENT_PROVIDER=gemini` — that puts the SQL retry loop on Gemini and will exhaust quota.

## 5. Health checks and startup

1. Supabase is hosted — no `pg_isready` gate unless you use the `local-db` Compose profile.
2. API startup:
   - `AGENT_PROVIDER=ollama`: ping `OLLAMA_HOST`, warn (do not crash) if unreachable
   - `AGENT_PROVIDER=nvidia`: no Ollama ping; a missing key surfaces on the first agent call
3. Frontend is static. Locally it uses `/api` via Vite/nginx. Vercel injects `VITE_API_BASE_URL` at build time.

`POST /chat` yields an SSE comment keepalive before `run_chat()` so Render does not look hung during the Gemini + NIM loop.

## 6. What does not change

- Database schema, roles, and allow-lists (`docs/schema-*.md`)
- Insight rule catalog and `copilot.alerts` (`docs/insight-rules.md`)
- Demo clock
- Frontend design system (`design-guidelines.md`)
- Orchestrator routing (`agentflow.md`)
