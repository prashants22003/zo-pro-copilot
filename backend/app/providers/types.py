from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    properties: dict[str, str]
    required: list[str]


@dataclass
class ToolCall:
    name: str
    args: dict
    id: str = ""
    thought_signature: bytes | str | None = None


@dataclass
class ChatMessage:
    role: str
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_result: str | None = None
    model_parts: list[dict] = field(default_factory=list)


@dataclass
class GenerateResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model_parts: list[dict] = field(default_factory=list)
