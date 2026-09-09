from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import get_settings
from .types import ChatMessage, GenerateResult, ToolCall, ToolSpec


def _host() -> str:
    return get_settings().ollama_host.rstrip("/")


def ping() -> bool:
    try:
        req = urllib.request.Request(_host() + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _tools_payload(tools: list[ToolSpec] | None) -> list[dict] | None:
    if not tools:
        return None
    out = []
    for spec in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            k: {"type": "string", "description": v} for k, v in spec.properties.items()
                        },
                        "required": spec.required,
                    },
                },
            }
        )
    return out


def _to_messages(system: str, messages: list[ChatMessage]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for msg in messages:
        if msg.role == "tool":
            row: dict = {"role": "tool", "content": msg.tool_result or ""}
            if msg.tool_name:
                row["name"] = msg.tool_name
            if msg.tool_call_id:
                row["tool_call_id"] = msg.tool_call_id
            out.append(row)
            continue
        if msg.role == "assistant" and msg.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": msg.text or "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": c.args or {},
                            },
                            **({"id": c.id} if c.id else {}),
                        }
                        for c in msg.tool_calls
                    ],
                }
            )
            continue
        role = "assistant" if msg.role == "assistant" else "user"
        out.append({"role": role, "content": msg.text or ""})
    return out


def _parse_args(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"value": data}
        except json.JSONDecodeError:
            return {"value": raw}
    return {"value": str(raw)}


def generate(
    system: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    model: str | None = None,
) -> GenerateResult:
    chosen = (model or get_settings().resolved_agent_model).strip()
    payload = {
        "model": chosen,
        "stream": False,
        "messages": _to_messages(system, messages),
    }
    tool_payload = _tools_payload(tools)
    if tool_payload:
        payload["tools"] = tool_payload
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _host() + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama is not reachable at {_host()}. Start Ollama on the host and pull {chosen}."
        ) from exc

    msg = data.get("message") or {}
    text = (msg.get("content") or "").strip()
    calls: list[ToolCall] = []
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function") or tc
        name = fn.get("name") or ""
        if not name:
            continue
        calls.append(
            ToolCall(
                name=name,
                args=_parse_args(fn.get("arguments")),
                id=str(tc.get("id") or f"call-{i}"),
            )
        )
    return GenerateResult(text=text, tool_calls=calls)
