# PRD — Zo-Pro Copilot

## 1. Summary

Zo-Pro Copilot is a chat-based copilot over an enterprise’s relational sales and purchasing data. A person asks in plain language and gets an answer grounded in live query results, with a path to the underlying rows in one motion. It also surfaces findings that genuinely need attention — a projected stockout, unusual spend, a customer going quiet — without inventing concern the data does not support.

This document scopes the MVP: a working prototype against Wide World Importers on Postgres, meant to show the interaction model and multi-agent architecture to a reviewer. It is not a production deployment.

Working UI name in early mockups was “Current”. Product name is **Zo-Pro Copilot**.

## 2. Problem

Business teams that need a quick read on “how are we doing” today either:

- wait on an analyst or a dashboard that is a day stale and only answers the questions it was built for, or
- learn enough SQL/BI tooling to self-serve, which most stakeholders will not do

Real problems (a supplier delay about to cause a stockout, a margin quietly compressing on a product line) are found late, if at all, because nobody was looking at the right table at the right time.

## 3. Goal

Give a non-technical business user a conversational way to ask about sales and purchasing performance, get an answer grounded in actual query results, and be told about the handful of things in the data that warrant attention — with full transparency into where every number came from.

The product must **calculate metrics on demand**, not serve a fixed menu of questions. Reviewers can ask anything in the sales/purchasing domain; the system routes, queries, and explains.

## 4. Target user

Primary: a business stakeholder who owns or cares about sales/purchasing outcomes and does not write SQL.

Secondary: a technical evaluator judging whether the architecture is sound enough to build on.

## 5. Scope — MVP

### In scope

- Chat interface, single conversation thread, no multi-session history
- No login; desktop-first, designed for **1440px** width, shareable demo link later
- Two domain agents (Sales, Purchase), each with a **table allow-list** and a read-only Postgres role, generating and executing SQL against seeded Wide World Importers data
- An orchestrator that routes a question to the right agent (or both), holds a catalog of *what to look for and where*, and synthesizes the final answer
- An Insight Agent with the **full advanced rule catalog** in `docs/insight-rules.md` (deterministic SQL/Python; card text uses the rule template by default, optional LLM narration)
- **Demo clock**: an adjustable “as of” date. The product ignores all transactional data after that date and resolves “last month / last quarter / this week / FY quarter” against it. Fiscal year = **calendar year** (Q1 Jan–Mar)
- Clock-only questions (what date, which FY/quarter/month) are answered from the demo clock **without calling an LLM or running SQL**
- Drill-down: click an insight card or chart → chat column shrinks, a fragment of the clicked card extracts and morphs into a **data pane** (tabs for multiple dashboards: live chart from the query rows, KPIs, table, SQL on demand). User can keep chatting
- Streaming text responses
- Visual system in `design-guidelines.md` (mock HTML is visual reference only; MVP layout is the split-chat, not a popup)
- One `docker compose up`: if Postgres is healthy and empty, seed from `data/WideWorldImporters-Full.bak`; if already seeded, skip

### Out of scope for MVP

- Write access to source data
- Multi-user auth or permissions beyond DB-level agent roles
- Persisted conversation history across sessions
- Real enterprise connectors (this MVP is the seeded sample only)
- Mobile-optimized layout
- Production job scheduler for insights (on session start or a simple interval)
- Hardcoded question → answer pairs **for business metrics**. Example questions in docs are **capability coverage**, not the product’s script. Clock/FY/as-of facts derived from `demo_clock` are the exception
- True ML forecasting. “How will next quarter look?” is a **disclosed suggestion** from trailing metrics, not a predictive model

## 6. Key user flows

1. **Ask a clock/FY question** (what date, which quarter, which financial year) → answered from the demo clock with no LLM and no SQL. Changing the clock changes the answer.
2. **Ask a metric question** → orchestrator routes to Sales and/or Purchase → agent generates SQL (filtered by demo clock), executes under its role, returns rows → orchestrator streams a natural-language answer with source tables. Follow-ups reuse conversation context; metric questions are not pre-written.
3. **See a proactive insight** → on session start, orchestrator reads `copilot.alerts` populated by the Insight Agent’s rule layer (evaluated as of the demo clock) → live alerts render as insight cards in the thread.
4. **Drill into a claim** → user clicks a card or chart → shared-element motion: chat shrinks left, a fragment of the clicked article extracts and becomes a tab in the data pane (live chart from the result set + rows + SQL). Further clicks open additional tabs. Closing the last tab reverses the motion.
5. **Follow-up** → user asks about what is on screen or in the last answer → orchestrator keeps subject, clock, and open-tab context without the user restating them.
6. **Look ahead** → user asks how the business might perform next period → agents pull trailing metrics; orchestrator states a suggestion **and the metrics used**. Never presented as a guaranteed forecast.

## 7. Success criteria

- A reviewer can ask **unscripted** sales/purchasing questions (performance, region, monthly money in, suppliers, stock, margin) and get correct, source-cited answers
- Clock/FY/as-of questions are correct even when the LLM is down or over quota
- Metric questions compute from the database as of the demo clock; changing the clock changes answers
- At least two insight types (one warning, one positive) fire on the seeded data and are grounded (tables + inspectable SQL)
- Split-chat drill-down is smooth at 1440px: no popup, no disconnected modal, tabs for multiple datasets, chat remains usable
- A technical reviewer can see clear separation: orchestrator, Sales agent, Purchase agent, Insight agent, and DB access boundaries — not one monolithic prompt

## 8. Technical stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite, Tailwind (design tokens), Framer Motion | Shared-element split-chat is the main design focus |
| Streaming | Server-Sent Events | One-way token stream from backend to chat |
| Backend | Python + FastAPI | Async streaming; LLM SDKs and data tooling |
| LLM | Orchestrator: **Gemini** Flash (`ORCH_PROVIDER=gemini`). Domain agents: **Ollama** coder on the host. Tests mock LLMs and never spend Gemini quota. | Gemini talks to the user and assigns agents; Qwen writes SQL. Direct tool-calling, no orchestration framework |
| Insight text | Rule templates by default (`INSIGHT_NARRATE=template`); optional LLM narration | Insights stay deterministic; narration must not spend chat quota |
| Database | PostgreSQL | App database; WWI migrated from the SQL Server `.bak` |
| Source backup | `data/WideWorldImporters-Full.bak` (~124 MB, OLTP Full) | Canonical seed |
| Agent-to-DB | Allow-listed tables; roles `sales_agent_role`, `purchase_agent_role`; SELECT only; timeout + row cap | Least privilege in the database, not only in the prompt |
| Insight detection | Deterministic rule layer → `copilot.alerts`; template text by default | No LLM-invented concern |
| Time | Demo clock (env + header control) | Makes 2013–2016 WWI data demoable; cutoff is inclusive |
| Infra | Docker Compose (Postgres + restore dump if empty + API + frontend) | One command locally; same stack for a shared demo link |

## 9. Risks

- **Text-to-SQL**: the active provider can write wrong SQL. Mitigation: tight schema docs, allow-lists, retry on execution error, never invent numbers when `confidence` is `no_data`. Local Ollama models are weaker at tools than Gemini; hosted demo should use Gemini.
- **Gemini quota**: orchestrator only (about two Flash calls per question, model `gemini-3.6-flash`). Domain SQL stays on Ollama. Clock-only questions and insight templates must not consume quota.
- **Ollama must be running on the host** for Sales/Purchase SQL. The API container talks to `host.docker.internal:11434`; Ollama is not in Compose.
- **Insight rules vs real WWI**: every rule in `docs/insight-rules.md` must be verified to fire or stay silent correctly after seed — not assumed.
- **Holdings snapshot vs clock**: `warehouse.stock_item_holdings` is end-state in the backup. Stock-as-of-clock must be reconstructed from `warehouse.stock_item_transactions` (see `docs/data-setup.md`).
- **Cross-domain joins**: orchestrator must use `cross_domain_query` when two result sets cannot be joined in reasoning.

## 10. Milestones

1. Postgres migrate-if-empty from the `.bak`, roles, demo clock, schema allow-lists
2. Orchestrator + Sales + Purchase answering unscripted single-domain questions (no UI polish)
3. Insight Agent advanced catalog running as of the clock; `copilot.alerts` verified
4. Frontend to `design-guidelines.md`, SSE, demo-clock control
5. Split-chat drill-down + tabs wired to real query results
6. End-to-end: insights on load, follow-ups, split-chat, cross-domain, “next period” suggestion with disclosed metrics

Target submission: **9 August, morning**. If that date is already past the working calendar, confirm **9 September** before treating the deadline as firm.

## 11. Document map

| Doc | Role |
|---|---|
| `prd.md` | This file — product scope |
| `design-guidelines.md` | Visual system and split-chat motion |
| `agentflow.md` | Orchestrator, agents, routing, allow-lists |
| `docs/architecture.md` | Compose, services, env, health, seed-if-empty |
| `docs/data-setup.md` | `.bak` → SQL Server → Postgres, clock, cutoff |
| `docs/schema-sales.md` | Sales allow-list, joins, where to look |
| `docs/schema-purchasing.md` | Purchasing allow-list |
| `docs/schema-warehouse.md` | Stock items, holdings, transactions |
| `docs/schema-application.md` | People, geography (region questions) |
| `docs/insight-rules.md` | Advanced deterministic catalog |
| `docs/api.md` | HTTP/SSE contracts |
| `docs/evaluation.md` | Capability coverage (not a hardcoded script) |
| `docs/decisions.md` | Locked decisions |
