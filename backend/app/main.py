from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agents.insight import list_alerts, refresh_alerts
from .agents.orchestrator import run_chat
from .agents.domain import run_cross_domain
from .allowlists import INSIGHT_TABLES, display_names
from .cards import alert_to_card
from .config import get_settings
from .db import get_clock, is_seeded, order_date_bounds, set_clock
from .sql_guard import SqlGuardError, cap_sql, referenced_tables, validate_select
from .visualize import present

app = FastAPI(title="Zo-Pro Copilot")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


class ClockIn(BaseModel):
    demo_clock: date


class DrillIn(BaseModel):
    sql_executed: str
    title: str = "Query results"
    origin_card_id: str | None = None
    subject_key: str | None = None


def _clock_payload(clock: date) -> dict[str, Any]:
    lo, hi = order_date_bounds()
    return {
        "demo_clock": clock.isoformat(),
        "data_min": lo.isoformat() if lo else None,
        "data_max": hi.isoformat() if hi else None,
    }


@app.on_event("startup")
def _startup():
    agent = settings.resolved_agent_provider
    if agent == "ollama":
        from .llm import llm_available

        if not llm_available("agent"):
            print(
                f"WARNING: Ollama is not reachable at {settings.ollama_host}",
                flush=True,
            )
    else:
        print(f"agent provider {agent} (no local Ollama ping)", flush=True)
    if not is_seeded():
        print("WARNING: database does not look seeded", flush=True)
        return
    clock = get_clock()
    try:
        refresh_alerts(clock)
        print(f"insights refreshed for {clock}", flush=True)
    except Exception as exc:
        print(f"insight refresh failed: {exc}", flush=True)


@app.get("/health")
def health():
    seeded = is_seeded()
    clock = get_clock() if seeded else None
    return {
        "ok": seeded,
        "postgres": "ready" if seeded else "empty",
        "seeded": seeded,
        "demo_clock": clock.isoformat() if clock else None,
    }


@app.get("/clock")
def read_clock():
    return _clock_payload(get_clock())


@app.patch("/clock")
def patch_clock(body: ClockIn):
    lo, hi = order_date_bounds()
    if lo and body.demo_clock < lo:
        raise HTTPException(400, f"Date is before the data range ({lo}).")
    if hi and body.demo_clock > hi:
        raise HTTPException(400, f"Date is after the data range ({hi}).")
    clock = set_clock(body.demo_clock)
    refresh_alerts(clock)
    return _clock_payload(clock)


@app.get("/alerts")
def alerts():
    clock = get_clock()
    items = list_alerts(clock)
    if not items:
        items = refresh_alerts(clock)
    cards = [alert_to_card(a) for a in items]
    return {"alerts": cards, "demo_clock": clock.isoformat()}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/chat")
def chat(body: ChatIn):
    def gen():
        yield ": keepalive\n\n"
        try:
            result = run_chat(body.message, body.history)
        except Exception as exc:
            yield _sse(
                "error",
                {"message": f"The language model could not complete that turn. {exc}"},
            )
            yield _sse("done", {"message_id": "err"})
            return
        if result.get("error"):
            yield _sse("error", {"message": result["error"]})
            yield _sse("done", {"message_id": "err"})
            return
        words = (result.get("answer") or "").split()
        chunk = []
        for i, w in enumerate(words):
            chunk.append(w)
            if len(chunk) >= 3 or i == len(words) - 1:
                yield _sse("token", {"text": " ".join(chunk) + (" " if i < len(words) - 1 else "")})
                chunk = []
        for card in result.get("cards") or []:
            yield _sse("card", card)
        if result.get("sources"):
            yield _sse("sources", {"display_sources": result["sources"]})
        if result.get("metrics_used"):
            yield _sse("metrics_used", {"metrics": result["metrics_used"]})
        yield _sse("done", {"message_id": "m"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/drilldown")
def drilldown(body: DrillIn):
    try:
        clean = validate_select(body.sql_executed, INSIGHT_TABLES)
    except SqlGuardError as exc:
        raise HTTPException(400, str(exc)) from exc
    capped = cap_sql(clean, get_settings().query_row_cap)
    from .db import insight_conn, jsonable_row

    try:
        with insight_conn() as conn:
            cur = conn.execute(capped)
            cols = [d.name for d in cur.description]
            rows = [jsonable_row(r) for r in cur.fetchall()]
    except Exception as exc:
        raise HTTPException(400, f"Query failed: {exc}") from exc
    tables = referenced_tables(clean)
    columns = []
    for c in cols:
        sample = next((r[c] for r in rows if r.get(c) is not None), None)
        kind = "num" if isinstance(sample, (int, float)) else "text"
        columns.append({"key": c, "label": c.replace("_", " "), "kind": kind})
    viz = present(rows, body.subject_key)
    return {
        "tab_id": f"tab-{body.origin_card_id or 'x'}",
        "title": body.title,
        "breadcrumb": " · ".join(display_names(tables)) or "Query",
        "sql_executed": clean,
        "columns": columns,
        "rows": [[row.get(c["key"]) for c in columns] for row in rows],
        "flagged_row_indexes": viz["flagged_row_indexes"],
        "kpis": viz["kpis"],
        "chart": viz["chart"],
    }
