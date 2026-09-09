from __future__ import annotations

import json
import re

from .config import get_settings
from .providers import gemini as gemini_provider
from .providers import ollama as ollama_provider
from .providers.types import ChatMessage, GenerateResult, ToolCall, ToolSpec

_TOOL_TAG = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.S | re.I)

__all__ = [
    "ChatMessage",
    "GenerateResult",
    "ToolCall",
    "ToolSpec",
    "generate",
    "function_calls",
    "text_of",
    "parse_json_block",
    "llm_available",
    "unavailable_message",
    "sales_tools",
    "purchase_tools",
    "orchestrator_tools",
    "provider_for_role",
    "model_for_role",
]


def provider_for_role(role: str = "orchestrator") -> str:
    settings = get_settings()
    if role == "agent":
        return settings.resolved_agent_provider
    return settings.resolved_orch_provider


def model_for_role(role: str = "orchestrator") -> str:
    settings = get_settings()
    if role == "agent":
        return settings.resolved_agent_model
    return settings.resolved_orch_model


def _provider_ready(provider: str) -> bool:
    settings = get_settings()
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    return ollama_provider.ping()


def llm_available(role: str | None = None) -> bool:
    if role:
        return _provider_ready(provider_for_role(role))
    return _provider_ready(provider_for_role("orchestrator"))


def unavailable_message(role: str = "orchestrator") -> str:
    settings = get_settings()
    provider = provider_for_role(role)
    model = model_for_role(role)
    if provider == "gemini":
        return "Gemini is not configured. Add GEMINI_API_KEY to .env and restart the API."
    return (
        f"Ollama is not reachable at {settings.ollama_host}. "
        f"Start Ollama on the host and run: ollama pull {model}"
    )


def sales_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="execute_sql",
            description=(
                "Run a single SELECT against the sales allow-list. "
                "Qualify tables as schema.table. Always filter dates <= demo clock."
            ),
            properties={"query": "PostgreSQL SELECT statement"},
            required=["query"],
        )
    ]


def purchase_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="execute_sql",
            description=(
                "Run a single SELECT against the purchasing allow-list. "
                "Qualify tables as schema.table. Always filter dates <= demo clock."
            ),
            properties={"query": "PostgreSQL SELECT statement"},
            required=["query"],
        )
    ]


def orchestrator_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="sales_agent",
            description=(
                "Ask the Sales agent to query invoiced/booked sales, customers, regions, "
                "or profit (sales.invoice_lines.line_profit). Pass a precise brief, not SQL."
            ),
            properties={"question": "Brief for the sales agent, including period and metric"},
            required=["question"],
        ),
        ToolSpec(
            name="purchase_agent",
            description=(
                "Ask the Purchase agent to query suppliers, purchase orders, spend, "
                "stock on hand, or overdue receipts. Pass a precise brief, not SQL."
            ),
            properties={"question": "Brief for the purchase agent, including period and metric"},
            required=["question"],
        ),
        ToolSpec(
            name="get_live_alerts",
            description="Read current rule-layer alerts for the demo clock. Do not invent new warnings.",
            properties={},
            required=[],
        ),
        ToolSpec(
            name="cross_domain_query",
            description=(
                "Last resort: one read-only SELECT that joins sales and purchasing tables. "
                "Use only when both domain agents cannot answer with separate result sets."
            ),
            properties={"query": "PostgreSQL SELECT with schema.table qualifiers"},
            required=["query"],
        ),
    ]


def _tool_from_mapping(data: dict, allowed: set[str] | None) -> ToolCall | None:
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    if allowed is not None and name not in allowed:
        return None
    args = data.get("arguments") if "arguments" in data else data.get("parameters")
    if args is None:
        args = {}
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            args = parsed if isinstance(parsed, dict) else {"question": args}
        except json.JSONDecodeError:
            lowered = args.lower()
            args = {"query": args} if "select" in lowered else {"question": args}
    if not isinstance(args, dict):
        args = {"value": str(args)}
    return ToolCall(name=name, args=args)


def parse_embedded_tool_calls(text: str, allowed: set[str] | None = None) -> list[ToolCall]:
    """Read tool calls the model wrote as JSON/XML in the message body (common with Ollama)."""
    if not (text or "").strip():
        return []
    found: list[ToolCall] = []
    seen: set[str] = set()

    def add(obj: dict | None) -> None:
        if not isinstance(obj, dict):
            return
        call = _tool_from_mapping(obj, allowed)
        if not call:
            return
        key = f"{call.name}:{json.dumps(call.args, sort_keys=True)}"
        if key in seen:
            return
        seen.add(key)
        found.append(call)

    for block in _TOOL_TAG.findall(text):
        add(parse_json_block(block))
        for obj in _json_objects(block):
            add(obj)
    for obj in _json_objects(text):
        add(obj)
    return found


def _json_objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    out: list[dict] = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        i = end
    return out


def generate(
    system: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    role: str = "orchestrator",
) -> GenerateResult:
    provider = provider_for_role(role)
    model = model_for_role(role)
    if provider == "gemini":
        result = gemini_provider.generate(system, messages, tools, model=model)
    else:
        result = ollama_provider.generate(system, messages, tools, model=model)
    if result.tool_calls:
        return result
    if not tools:
        return result
    allowed = {t.name for t in tools}
    embedded = parse_embedded_tool_calls(result.text, allowed)
    if not embedded:
        return result
    return GenerateResult(text="", tool_calls=embedded)


def function_calls(response: GenerateResult) -> list[ToolCall]:
    return list(response.tool_calls or [])


def text_of(response: GenerateResult) -> str:
    return (response.text or "").strip()


def parse_json_block(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None
