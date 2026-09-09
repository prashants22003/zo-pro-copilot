from app.llm import parse_embedded_tool_calls, parse_json_block


def test_qwen_content_json_is_a_tool_call() -> None:
    text = (
        '{"name": "execute_sql", "arguments": {"query": '
        '"SELECT SUM(il.extended_price) FROM sales.invoice_lines il"}}'
    )
    calls = parse_embedded_tool_calls(text, {"execute_sql", "get_live_alerts"})
    assert len(calls) == 1
    assert calls[0].name == "execute_sql"
    assert "invoice_lines" in calls[0].args["query"]


def test_tool_xml_block() -> None:
    text = """I'll look that up.
<tool_call>
{"name": "execute_sql", "arguments": {"query": "SELECT 1"}}
</tool_call>
"""
    calls = parse_embedded_tool_calls(text, {"execute_sql"})
    assert [c.name for c in calls] == ["execute_sql"]
    assert calls[0].args["query"] == "SELECT 1"


def test_answer_json_is_not_a_tool() -> None:
    text = '{"answer": "Sales were $4.5M last month.", "source_tables": ["sales.invoices"]}'
    assert parse_embedded_tool_calls(text, {"execute_sql"}) == []
    payload = parse_json_block(text)
    assert payload["answer"].startswith("Sales were")


def test_two_json_objects_in_one_blob() -> None:
    text = (
        '{"name": "execute_sql", "arguments": {"query": "SELECT 1"}}\n\n'
        '{"name": "get_live_alerts", "arguments": {}}'
    )
    calls = parse_embedded_tool_calls(text, {"execute_sql", "get_live_alerts"})
    assert [c.name for c in calls] == ["execute_sql", "get_live_alerts"]
    assert calls[0].args["query"] == "SELECT 1"


def test_unknown_tool_name_ignored() -> None:
    text = '{"name": "sales_agent", "arguments": {"question": "last quarter"}}'
    assert parse_embedded_tool_calls(text, {"execute_sql", "get_live_alerts"}) == []
