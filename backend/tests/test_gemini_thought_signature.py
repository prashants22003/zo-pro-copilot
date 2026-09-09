from google.genai import types

from app.providers.gemini import _to_contents, dump_model_parts
from app.providers.types import ChatMessage, ToolCall


def test_dump_and_replay_keeps_thought_signature() -> None:
    sig = b"thought-sig-bytes"
    part = types.Part(
        function_call=types.FunctionCall(name="sales_agent", args={"question": "January 2015"}),
        thought_signature=sig,
    )
    dumped = dump_model_parts([part])
    assert dumped[0]["thought_signature"] == sig
    assert dumped[0]["function_call"]["name"] == "sales_agent"

    contents = _to_contents(
        [
            ChatMessage(role="user", text="how was our performance in january 2015?"),
            ChatMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        name="sales_agent",
                        args={"question": "January 2015"},
                        thought_signature=sig,
                    )
                ],
                model_parts=dumped,
            ),
            ChatMessage(role="tool", tool_name="sales_agent", tool_result='{"rows": []}'),
        ]
    )
    model = contents[1]
    assert model.role == "model"
    replayed = model.parts[0]
    assert replayed.thought_signature == sig
    assert replayed.function_call.name == "sales_agent"


def test_tool_call_signature_used_without_model_parts() -> None:
    sig = b"only-on-toolcall"
    contents = _to_contents(
        [
            ChatMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(name="sales_agent", args={"question": "q"}, thought_signature=sig)
                ],
            )
        ]
    )
    assert contents[0].parts[0].thought_signature == sig
