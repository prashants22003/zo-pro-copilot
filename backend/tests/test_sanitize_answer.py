from app.sanitize import is_leaked_model_text, sanitize_user_answer


def test_execute_sql_json_is_leaked() -> None:
    text = (
        '{"name": "execute_sql", "arguments": {"query": '
        '"SELECT SUM(t.transaction_amount) FROM purchasing.supplier_transactions t"}}'
    )
    assert is_leaked_model_text(text)
    assert sanitize_user_answer(text, "Line profit is 12.") == "Line profit is 12."


def test_fenced_sql_is_leaked() -> None:
    text = "```sql\nSELECT SUM(line_profit) FROM sales.invoice_lines\n```"
    assert is_leaked_model_text(text)
    assert sanitize_user_answer(text, "fallback") == "fallback"


def test_sales_agent_json_is_leaked() -> None:
    text = '{"name": "sales_agent", "arguments": {"question": "March profit"}}'
    assert is_leaked_model_text(text)


def test_plain_insight_kept() -> None:
    text = "Invoiced line profit for March 2015 was 1,200,000, from Sales.InvoiceLines."
    assert not is_leaked_model_text(text)
    assert sanitize_user_answer(text, "x") == text


def test_answer_json_unwraps() -> None:
    text = '{"answer": "Sales were $4.5M last month.", "source_tables": ["sales.invoices"]}'
    assert sanitize_user_answer(text, "x") == "Sales were $4.5M last month."


def test_empty_uses_fallback() -> None:
    assert sanitize_user_answer("", "kpi sentence") == "kpi sentence"
    assert sanitize_user_answer(None, "kpi sentence") == "kpi sentence"
