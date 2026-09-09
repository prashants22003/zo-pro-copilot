from __future__ import annotations

import json
import re
from datetime import date

from ..cards import alert_to_card, card_from_query_result, dedupe_cards
from ..clock import prompt_windows
from ..clock_intent import clock_only_answer
from ..db import get_clock
from ..llm import (
    ChatMessage,
    GenerateResult,
    ToolCall,
    generate,
    llm_available,
    orchestrator_tools,
    text_of,
    unavailable_message,
)
from ..metrics import compose_brief, match_metric, metrics_prompt, sources_match_contract, template_from_kpis
from ..sanitize import is_leaked_model_text, sanitize_user_answer
from ..sql_guard import SqlGuardError
from .domain import run_cross_domain, run_domain_agent
from .insight import list_alerts


ORCH_SYSTEM = """You are Zo-Pro Copilot, talking to a business user about Wide World Importers.
You never invent numbers. You never write SQL except via cross_domain_query, and only when a real join is required.

You assign work. Call sales_agent and/or purchase_agent with a precise brief (period, metric, grain).
When they ask what needs attention, call get_live_alerts — do not invent warnings.
Call both domain agents for margin / buy-vs-sell. Do not call execute_sql; that tool is not yours.

{metrics}

{windows}

Write the user-facing answer only after you have the agent results. Speak as first person, calm, concise. Put the numbers in the prose.
Never mention agents, tools, function calls, JSON, SQL, or that you are about to query.
If the question is outside sales, purchasing, warehouse, or the demo clock, say so without calling an agent.
"""

_ALERT_ASK = re.compile(r"need(s)? attention|what.?s wrong|alerts?|what should I look", re.I)


def _history_messages(history: list[dict]) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for item in history[-12:]:
        role = "user" if item.get("role") == "user" else "assistant"
        text = item.get("content") or ""
        if role == "assistant":
            text = sanitize_user_answer(text, fallback="")
            if not text:
                continue
        out.append(ChatMessage(role=role, text=text))
    return out


def _fallback_calls(message: str) -> list[ToolCall]:
    if _ALERT_ASK.search(message or ""):
        return [ToolCall(name="get_live_alerts", args={})]
    metric = match_metric(message)
    if not metric:
        return []
    question = message
    if metric["domain"] == "sales":
        return [ToolCall(name="sales_agent", args={"question": question})]
    if metric["domain"] == "purchase":
        return [ToolCall(name="purchase_agent", args={"question": question})]
    return [
        ToolCall(name="sales_agent", args={"question": question}),
        ToolCall(name="purchase_agent", args={"question": question}),
    ]


def _compact_tool_result(result: dict) -> dict:
    return {
        "error": result.get("error"),
        "rejected": result.get("rejected"),
        "row_count": result.get("row_count") or len(result.get("rows") or []),
        "rows": (result.get("rows") or [])[:20],
        "display_sources": result.get("display_sources") or [],
        "source_tables": result.get("source_tables") or [],
        "metrics_used": result.get("metrics_used") or [],
        "confidence": result.get("confidence"),
        "answer": result.get("answer") if not is_leaked_model_text(str(result.get("answer") or "")) else None,
    }


def _run_domain(domain: str, question: str, clock: date, user_message: str) -> dict:
    if not llm_available("agent"):
        return {"error": unavailable_message("agent"), "rows": [], "sql_executed": [], "source_tables": []}
    metric = match_metric(user_message) or match_metric(question)
    if metric and metric["domain"] not in {domain, "both"} and domain != "both":
        # still run — the orchestrator chose this agent; keep the agent's own brief
        pass
    brief = compose_brief(question, metric if metric and metric["domain"] in {domain, "both"} else None)
    result = run_domain_agent(domain=domain, question=brief, context="", clock=clock)
    check = metric if metric and metric["domain"] in {domain, "both"} else None
    if check and not sources_match_contract(result.get("source_tables"), check):
        retry_brief = compose_brief(question, check, retry=True)
        result = run_domain_agent(domain=domain, question=retry_brief, context="", clock=clock)
        if not sources_match_contract(result.get("source_tables"), check):
            result = dict(result)
            result["rejected"] = True
            result["error"] = result.get("error") or (
                f"The {domain} agent did not use the tables required for {check['id']}."
            )
    return result


def _call_tool(name: str, args: dict, clock: date, user_message: str) -> dict:
    if name == "sales_agent":
        question = args.get("question") or args.get("query") or user_message
        return _run_domain("sales", str(question), clock, user_message)
    if name == "purchase_agent":
        question = args.get("question") or args.get("query") or user_message
        return _run_domain("purchase", str(question), clock, user_message)
    if name == "get_live_alerts":
        return {"alerts": list_alerts(clock)}
    if name == "cross_domain_query":
        query = args.get("query") or args.get("sql") or ""
        try:
            result = run_cross_domain(query, clock)
            metric = match_metric(user_message)
            if metric and not sources_match_contract(result.get("source_tables"), metric):
                result = dict(result)
                result["rejected"] = True
                result["error"] = "Cross-domain query did not match the metric contract."
            return result
        except (SqlGuardError, Exception) as exc:
            return {"error": str(exc), "rows": [], "sql_executed": [], "source_tables": []}
    if name == "execute_sql":
        return {"error": "The orchestrator cannot run SQL. Assign sales_agent or purchase_agent."}
    return {"error": f"Unknown tool {name}"}


def _cards_from_tool(name: str, result: dict, user_message: str) -> list[dict]:
    if name == "get_live_alerts":
        return [alert_to_card(a) for a in (result.get("alerts") or [])]
    if result.get("rejected") or result.get("error"):
        return []
    metric = match_metric(user_message)
    title = metric["title"] if metric else "Result"
    if name == "sales_agent":
        title = (metric["title"] if metric and metric["domain"] in {"sales", "both"} else None) or "Sales"
    elif name == "purchase_agent":
        title = (metric["title"] if metric and metric["domain"] in {"purchase", "both"} else None) or "Purchasing"
    card = card_from_query_result(result, title=title)
    return [card] if card else []


def _template_answer(cards: list[dict], sources: list[str], user_message: str) -> str:
    kpis: list[dict] = []
    for card in cards:
        kpis.extend(card.get("metrics") or [])
    metric = match_metric(user_message)
    title = metric["title"] if metric else None
    if kpis:
        return template_from_kpis(kpis[:4], sources, title=title)
    if any(c.get("text") for c in cards):
        return cards[0]["text"]
    return "I could not compute that from the sales and purchasing tables."


def run_chat(message: str, history: list[dict]) -> dict:
    clock = get_clock()
    hit = clock_only_answer(message, clock)
    if hit:
        return hit
    if not llm_available("orchestrator"):
        return {
            "error": unavailable_message("orchestrator"),
            "cards": [],
            "sources": [],
            "metrics_used": [],
        }

    messages = _history_messages(history)
    messages.append(ChatMessage(role="user", text=message))
    system = ORCH_SYSTEM.format(windows=prompt_windows(clock), metrics=metrics_prompt())
    tools = orchestrator_tools()
    cards: list[dict] = []
    sources: list[str] = []
    metrics_used: list[str] = []
    sqls: list[str] = []

    resp = generate(system, messages, tools, role="orchestrator")
    native_calls = list(resp.tool_calls or [])
    calls = native_calls or _fallback_calls(message)

    if calls:
        messages.append(
            ChatMessage(
                role="assistant",
                text=resp.text,
                tool_calls=calls,
                model_parts=list(resp.model_parts or []),
            )
        )
        for call in calls:
            args = dict(call.args or {})
            result = _call_tool(call.name, args, clock, message)
            for src in result.get("display_sources") or []:
                if src not in sources:
                    sources.append(src)
            for item in result.get("metrics_used") or []:
                if item not in metrics_used:
                    metrics_used.append(item)
            for stmt in result.get("sql_executed") or []:
                sqls.append(stmt)
            cards.extend(_cards_from_tool(call.name, result, message))
            messages.append(
                ChatMessage(
                    role="tool",
                    tool_name=call.name,
                    tool_call_id=call.id,
                    tool_result=json.dumps(_compact_tool_result(result), default=str)[:12000],
                )
            )
        if native_calls:
            resp = generate(
                system
                + "\nThe agent results are in. Write the user-facing answer from those results only. "
                "If a query was rejected or errored, say what you could not compute. Do not emit JSON or SQL.",
                messages,
                tools=None,
                role="orchestrator",
            )
        else:
            resp = GenerateResult(text="")

    cards = dedupe_cards(cards)
    fallback = _template_answer(cards, sources, message) if (calls or cards) else (
        "I can help with sales, purchasing, and stock as of the demo clock."
    )
    answer = sanitize_user_answer(text_of(resp), fallback) or fallback
    return {
        "answer": answer,
        "cards": cards,
        "sources": sources,
        "metrics_used": metrics_used,
        "sqls": sqls,
    }
