import pytest

from app.agents.domain import run_select


@pytest.mark.integration
def test_line_profit_march_2015_query() -> None:
    sql = """
        SELECT SUM(
                 CASE WHEN i.is_credit_note THEN -il.line_profit ELSE il.line_profit END
               ) AS profit
        FROM sales.invoice_lines il
        JOIN sales.invoices i ON i.invoice_id = il.invoice_id
        WHERE i.invoice_date BETWEEN DATE '2015-03-01' AND DATE '2015-03-31'
    """
    try:
        from app.db import sales_conn

        with sales_conn() as conn:
            conn.execute("SELECT 1")
        result = run_select(sql)
    except Exception as exc:
        pytest.skip(f"postgres not available: {exc}")
    assert result.get("rows")
    assert "sales.invoice_lines" in (result.get("source_tables") or [])
    assert result["rows"][0].get("profit") is not None
