from __future__ import annotations

import json
from datetime import date

from ..allowlists import display_names, INSIGHT_TABLES, PURCHASE_TABLES, SALES_TABLES
from ..clock import prompt_windows
from ..config import get_settings
from ..db import insight_conn, jsonable_row, purchase_conn, sales_conn
from ..llm import ChatMessage, generate, parse_json_block, purchase_tools, sales_tools, text_of
from ..schema_context import load_schema
from ..sql_guard import cap_sql, referenced_tables, validate_select, SqlGuardError


def _run_sql(sql: str, allow, factory) -> tuple[list[dict], str, list[str]]:
    clean = validate_select(sql, allow)
    capped = cap_sql(clean, get_settings().query_row_cap)
    with factory() as conn:
        rows = [jsonable_row(r) for r in conn.execute(capped).fetchall()]
    return rows, clean, referenced_tables(clean)


def pick_role(tables: list[str]):
    tset = set(tables)
    sales_specific = SALES_TABLES - PURCHASE_TABLES
    purch_specific = PURCHASE_TABLES - SALES_TABLES
    has_sales = bool(tset & sales_specific)
    has_purch = bool(tset & purch_specific)
    if has_sales and has_purch:
        return insight_conn, INSIGHT_TABLES
    if has_purch and not has_sales:
        return purchase_conn, PURCHASE_TABLES
    if has_sales and not has_purch:
        return sales_conn, SALES_TABLES
    if tset <= SALES_TABLES:
        return sales_conn, SALES_TABLES
    if tset <= PURCHASE_TABLES:
        return purchase_conn, PURCHASE_TABLES
    return insight_conn, INSIGHT_TABLES


def run_select(sql: str) -> dict:
    tables = referenced_tables(sql)
    factory, allow = pick_role(tables)
    rows, clean, srcs = _run_sql(sql, allow, factory)
    return {
        "rows": rows[:40],
        "sql_executed": [clean],
        "source_tables": srcs,
        "display_sources": display_names(srcs),
        "row_count": len(rows),
    }


def run_domain_agent(*, domain: str, question: str, context: str, clock: date) -> dict:
    if domain == "sales":
        allow = SALES_TABLES
        schema = load_schema("sales", "application", "warehouse")
        extra = (
            "You may read warehouse.stock_items for product names only. "
            "Do not query purchasing or stock holdings. "
            "Profit is sales.invoice_lines.line_profit joined to sales.invoices — "
            "never purchasing.supplier_transactions."
        )
    else:
        allow = PURCHASE_TABLES
        schema = load_schema("purchasing", "warehouse", "application")
        extra = (
            "On-hand as of the clock: "
            "SELECT * FROM warehouse.on_hand_as_of(DATE '{clock}') AS h. "
            "Do not use holdings.quantity_on_hand as historical stock."
        ).format(clock=clock.isoformat())

    system = f"""You are the {domain} agent for Zo-Pro Copilot.
You answer by writing PostgreSQL SELECT statements, then summarizing the rows.
Never invent numbers. If a query fails, fix it. Qualify every table as schema.table.
Stay on this domain's allow-list only.

{prompt_windows(clock)}
{extra}

Revenue (invoiced) uses sales.invoice_lines.extended_price joined to sales.invoices,
excluding is_credit_note. Booked value uses order_lines.quantity * unit_price.
Profit uses sales.invoice_lines.line_profit (cite that column). Do not treat supplier
transactions or tax_amount as profit.

Schema:
{schema}

When you are done, return JSON only:
{{
  "answer": "plain language summary",
  "source_tables": ["sales.invoices"],
  "confidence": "ok | partial | no_data",
  "metrics_used": ["optional names of metrics"],
  "chart": null
}}
Do not invent a chart. The server draws charts from the SQL rows.
Call execute_sql as needed (max a few queries)."""

    factory = sales_conn if domain == "sales" else purchase_conn

    tools = sales_tools() if domain == "sales" else purchase_tools()
    messages: list[ChatMessage] = [
        ChatMessage(role="user", text=f"Question: {question}\nContext: {context or '(none)'}")
    ]
    sqls: list[str] = []
    last_rows: list[dict] = []
    last_sources: list[str] = []

    for _ in range(4):
        resp = generate(system, messages, tools, role="agent")
        calls = resp.tool_calls
        if not calls:
            payload = parse_json_block(text_of(resp)) or {}
            answer = payload.get("answer") or text_of(resp)
            sources = payload.get("source_tables") or last_sources
            return {
                "answer": answer,
                "rows": last_rows[:40],
                "sql_executed": sqls,
                "source_tables": sources,
                "display_sources": display_names(
                    [s if "." in s else s for s in sources]
                    if sources
                    else last_sources
                ),
                "confidence": payload.get("confidence") or ("ok" if last_rows else "partial"),
                "metrics_used": payload.get("metrics_used") or [],
                "chart": None,
            }
        messages.append(ChatMessage(role="assistant", text=resp.text, tool_calls=calls))
        for call in calls:
            args = dict(call.args or {})
            query = args.get("query") or args.get("sql") or ""
            try:
                rows, clean, srcs = _run_sql(query, allow, factory)
                sqls.append(clean)
                last_rows = rows
                last_sources = srcs
                body = json.dumps({"sql": clean, "row_count": len(rows), "rows": rows[:40]}, default=str)
            except (SqlGuardError, Exception) as exc:
                body = json.dumps({"error": str(exc)})
            messages.append(
                ChatMessage(
                    role="tool",
                    tool_name=call.name,
                    tool_call_id=call.id,
                    tool_result=body,
                )
            )

    return {
        "answer": "I could not finish the query within the tool-call limit.",
        "rows": last_rows[:40],
        "sql_executed": sqls,
        "source_tables": last_sources,
        "display_sources": display_names(last_sources),
        "confidence": "no_data",
        "metrics_used": [],
        "chart": None,
    }


def run_cross_domain(sql: str, clock: date) -> dict:
    rows, clean, srcs = _run_sql(sql, INSIGHT_TABLES, insight_conn)
    return {
        "rows": rows[:80],
        "sql_executed": [clean],
        "source_tables": srcs,
        "display_sources": display_names(srcs),
    }
