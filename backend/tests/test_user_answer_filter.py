from app.llm import parse_json_block
from app.sanitize import sanitize_user_answer


def test_user_answer_filter_unwraps_answer_block() -> None:
    text = '{"answer": "Sales were $4.5M last month.", "source_tables": ["sales.invoices"]}'
    payload = parse_json_block(text)
    assert payload["answer"].startswith("Sales were")
    assert sanitize_user_answer(text, "x") == payload["answer"]


def test_user_answer_filter_drops_tool_blob() -> None:
    text = '{"name": "execute_sql", "arguments": {"query": "SELECT 1"}}'
    assert sanitize_user_answer(text, "from the rows") == "from the rows"
