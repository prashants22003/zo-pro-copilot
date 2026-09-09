from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import get_settings
from .types import ChatMessage, GenerateResult, ToolCall, ToolSpec


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
                            k: {"type": "string", "description": v}
                            for k, v in spec.properties.items()
                        },
                        "required": spec.required,
                    },
                },
            }
        )
    return out


def _to_messages(system: str, messages: list[ChatMessage]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for i, msg in enumerate(messages):
        if msg.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "content": msg.tool_result or "",
                    "tool_call_id": msg.tool_call_id or f"call-{i}",
                }
            )
            continue
        if msg.role == "assistant" and msg.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": msg.text or None,
                    "tool_calls": [
                        {
                            "id": c.id or f"call-{j}",
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.args or {}),
                            },
                        }
                        for j, c in enumerate(msg.tool_calls)
                    ],
                }
            )
            continue
        role = "assistant" if msg.role == "assistant" else "user"
        out.append({"role": role, "content": msg.text or ""})
    return out


def generate(
    system: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    model: str | None = None,
) -> GenerateResult:
    settings = get_settings()
    key = (settings.nvidia_api_key or "").strip()
    if not key:
        raise RuntimeError(
            "NVIDIA NIM is not configured. Add NVIDIA_API_KEY to .env and restart the API."
        )
    base = (settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1").rstrip("/")
    chosen = (model or settings.resolved_agent_model).strip()
    payload: dict = {
        "model": chosen,
        "stream": False,
        "max_tokens": 4096,
        "messages": _to_messages(system, messages),
    }
    tool_payload = _tools_payload(tools)
    if tool_payload:
        payload["tools"] = tool_payload
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"NVIDIA NIM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"NVIDIA NIM is not reachable at {base}.") from exc

    choices = data.get("choices") or []
    msg = (choices[0].get("message") if choices else None) or {}
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
