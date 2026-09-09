from __future__ import annotations

from google import genai
from google.genai import types

from ..config import get_settings
from .types import ChatMessage, GenerateResult, ToolCall, ToolSpec

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _to_gemini_tools(tools: list[ToolSpec] | None) -> list[types.Tool] | None:
    if not tools:
        return None
    decls = []
    for spec in tools:
        decls.append(
            types.FunctionDeclaration(
                name=spec.name,
                description=spec.description,
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        k: types.Schema(type=types.Type.STRING, description=v)
                        for k, v in spec.properties.items()
                    },
                    required=spec.required,
                ),
            )
        )
    return [types.Tool(function_declarations=decls)]


def dump_model_parts(parts) -> list[dict]:
    """Keep functionCall parts (and thought signatures) for the next Gemini turn."""
    out: list[dict] = []
    for part in parts or []:
        item: dict = {}
        sig = getattr(part, "thought_signature", None)
        if sig:
            item["thought_signature"] = sig
        if getattr(part, "thought", False):
            item["thought"] = True
        fc = getattr(part, "function_call", None)
        if fc:
            args = dict(fc.args) if fc.args else {}
            entry = {"name": fc.name or "", "args": args}
            fc_id = getattr(fc, "id", "") or ""
            if fc_id:
                entry["id"] = fc_id
            item["function_call"] = entry
        text = getattr(part, "text", None)
        if text:
            item["text"] = text
        if item:
            out.append(item)
    return out


def _part_from_dump(item: dict) -> types.Part:
    kwargs: dict = {}
    sig = item.get("thought_signature")
    if sig:
        kwargs["thought_signature"] = sig
    if item.get("thought"):
        kwargs["thought"] = True
    fc = item.get("function_call")
    if fc:
        fc_kwargs: dict = {"name": fc.get("name") or "", "args": fc.get("args") or {}}
        if fc.get("id"):
            fc_kwargs["id"] = fc["id"]
        kwargs["function_call"] = types.FunctionCall(**fc_kwargs)
    if "text" in item:
        kwargs["text"] = item["text"]
    return types.Part(**kwargs)


def _parts_from_tool_calls(msg: ChatMessage) -> list[types.Part]:
    if msg.model_parts:
        return [_part_from_dump(p) for p in msg.model_parts]
    parts: list[types.Part] = []
    if msg.text:
        parts.append(types.Part(text=msg.text))
    for i, call in enumerate(msg.tool_calls or []):
        kwargs: dict = {
            "function_call": types.FunctionCall(name=call.name, args=call.args or {}),
        }
        if call.thought_signature:
            kwargs["thought_signature"] = call.thought_signature
        parts.append(types.Part(**kwargs))
    return parts


def _to_contents(messages: list[ChatMessage]) -> list[types.Content]:
    contents: list[types.Content] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.role == "tool":
            parts = []
            while i < len(messages) and messages[i].role == "tool":
                parts.append(
                    types.Part.from_function_response(
                        name=messages[i].tool_name or "",
                        response={"result": messages[i].tool_result or ""},
                    )
                )
                i += 1
            contents.append(types.Content(role="user", parts=parts))
            continue
        if msg.role == "assistant" and (msg.tool_calls or msg.model_parts):
            contents.append(types.Content(role="model", parts=_parts_from_tool_calls(msg)))
        elif msg.role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=msg.text or "")]))
        else:
            contents.append(types.Content(role="user", parts=[types.Part(text=msg.text or "")]))
        i += 1
    return contents


def generate(
    system: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    model: str | None = None,
) -> GenerateResult:
    chosen = (model or get_settings().resolved_orch_model).strip()
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        tools=_to_gemini_tools(tools),
    )
    response = client().models.generate_content(
        model=chosen,
        contents=_to_contents(messages),
        config=config,
    )
    if not response.candidates:
        try:
            text = (response.text or "").strip()
        except Exception:
            text = ""
        return GenerateResult(text=text)

    raw_parts = response.candidates[0].content.parts or []
    model_parts = dump_model_parts(raw_parts)
    visible: list[str] = []
    calls: list[ToolCall] = []
    for part in raw_parts:
        fc = getattr(part, "function_call", None)
        if fc:
            args = dict(fc.args) if fc.args else {}
            calls.append(
                ToolCall(
                    name=fc.name or "",
                    args=args,
                    id=str(getattr(fc, "id", "") or ""),
                    thought_signature=getattr(part, "thought_signature", None),
                )
            )
            continue
        if getattr(part, "thought", False):
            continue
        text = getattr(part, "text", None)
        if text:
            visible.append(text)
    return GenerateResult(
        text="".join(visible).strip(),
        tool_calls=calls,
        model_parts=model_parts,
    )
