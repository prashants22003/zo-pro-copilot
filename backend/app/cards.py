from __future__ import annotations

import re
import uuid

from .visualize import present

_SQL_WS = re.compile(r"\s+")


def fingerprint_sql(sql: str | None) -> str:
    return _SQL_WS.sub(" ", (sql or "").strip().lower())


def fingerprint_card(card: dict) -> str:
    sql = fingerprint_sql(card.get("sql_executed") or "")
    if sql:
        return f"sql:{sql}"
    metrics = tuple((m.get("label"), m.get("value")) for m in card.get("metrics") or [])
    return f"kpi:{metrics}|title:{card.get('title')}"


def dedupe_cards(cards: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for card in cards:
        key = fingerprint_card(card)
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
    return out


def card_from_query_result(
    result: dict,
    *,
    title: str,
    category: str = "info",
) -> dict | None:
    if result.get("error") or result.get("rejected"):
        return None
    sqls = result.get("sql_executed") or []
    rows = result.get("rows") or []
    if not sqls or not rows:
        return None
    last_sql = sqls[-1] if isinstance(sqls[-1], str) else str(sqls[-1])
    viz = present(rows)
    kpis = viz.get("kpis") or []
    chart = viz.get("chart")
    summary = (
        f"{kpis[0]['value']} {kpis[0]['label']}" if kpis else f"{len(rows)} rows"
    )
    return {
        "id": f"card-{uuid.uuid4().hex[:10]}",
        "kind": "chart" if chart else "insight",
        "category": category,
        "title": title,
        "text": f"Tap to see the rows behind {summary}.",
        "metrics": kpis[:3],
        "display_sources": result.get("display_sources") or [],
        "sql_executed": last_sql,
        "chart": chart,
    }


def alert_to_card(alert: dict) -> dict:
    metrics = alert.get("metrics") or {}
    metric_row = []
    if isinstance(metrics, dict):
        for key in ("days_overdue", "days_of_cover", "days_silent", "pct", "share"):
            if key in metrics and metrics[key] is not None:
                val = metrics[key]
                if key in {"pct", "share"}:
                    metric_row.append(
                        {"value": f"{abs(float(val)) * 100:.0f}%", "label": key.replace("_", " ")}
                    )
                else:
                    metric_row.append({"value": str(int(float(val))), "label": key.replace("_", " ")})
    elif isinstance(metrics, list):
        metric_row = metrics[:2]
    category = alert.get("category") or "info"
    return {
        "id": f"alert-{alert.get('id') or uuid.uuid4().hex[:10]}",
        "kind": "insight",
        "category": category,
        "title": "Needs attention" if category == "warning" else "Worth noting",
        "text": alert.get("text") or "",
        "metrics": metric_row[:2],
        "display_sources": alert.get("display_sources") or [],
        "sql_executed": alert.get("sql_executed") or "",
        "subject_key": alert.get("subject_key"),
        "chart": None,
    }
