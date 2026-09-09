from __future__ import annotations

import re

from .llm import parse_embedded_tool_calls, parse_json_block

_TOOL_NAMES = {
    "execute_sql",
    "sales_agent",
    "purchase_agent",
    "get_live_alerts",
    "cross_domain_query",
}
_NAMED_TOOL = re.compile(
    r'"name"\s*:\s*"(execute_sql|sales_agent|purchase_agent|get_live_alerts|cross_domain_query)"'
)
_SQL = re.compile(r"\bselect\b[\s\S]{0,4000}\bfrom\b", re.I)
_FENCE = re.compile(r"^```")


def is_leaked_model_text(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _NAMED_TOOL.search(raw):
        return True
    if parse_embedded_tool_calls(raw, _TOOL_NAMES):
        return True
    payload = parse_json_block(raw)
    if payload:
        name = str(payload.get("name") or "")
        if name in _TOOL_NAMES:
            return True
        if "arguments" in payload and name:
            return True
        if "query" in payload and ("SELECT" in str(payload.get("query")).upper() or "select" in str(payload.get("query"))):
            if not isinstance(payload.get("answer"), str):
                return True
    if _FENCE.match(raw) and _SQL.search(raw):
        return True
    if raw.lower().lstrip().startswith("select") and _SQL.search(raw):
        return True
    return False


def sanitize_user_answer(text: str | None, fallback: str = "") -> str:
    raw = (text or "").strip()
    if not raw or is_leaked_model_text(raw):
        return (fallback or "").strip()
    payload = parse_json_block(raw)
    if payload and isinstance(payload.get("answer"), str) and payload["answer"].strip():
        inner = payload["answer"].strip()
        if is_leaked_model_text(inner):
            return (fallback or "").strip()
        return inner
    return raw
