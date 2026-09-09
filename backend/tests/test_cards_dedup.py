from app.cards import card_from_query_result, dedupe_cards


def _result(sql: str, value: float = -9015037.76) -> dict:
    return {
        "rows": [{"profit": value}],
        "sql_executed": [sql],
        "display_sources": ["Purchasing.SupplierTransactions"],
        "source_tables": ["purchasing.supplier_transactions"],
    }


def test_three_identical_sqls_one_card() -> None:
    sql = "SELECT SUM(t.transaction_amount) AS profit FROM purchasing.supplier_transactions t"
    cards = [card_from_query_result(_result(sql), title="Query results") for _ in range(3)]
    assert all(c is not None for c in cards)
    assert len(dedupe_cards(cards)) == 1


def test_two_different_grains_two_cards() -> None:
    a = card_from_query_result(
        _result("SELECT SUM(il.line_profit) AS profit FROM sales.invoice_lines il", 10.0),
        title="Line profit",
    )
    b = card_from_query_result(
        _result(
            "SELECT SUM(il.extended_price) AS revenue FROM sales.invoice_lines il",
            20.0,
        ),
        title="Invoiced revenue",
    )
    out = dedupe_cards([a, b, a])
    assert len(out) == 2


def test_no_hard_cap_of_three() -> None:
    cards = []
    for i in range(4):
        cards.append(
            card_from_query_result(
                _result(f"SELECT {i} AS n FROM sales.invoices", float(i)),
                title=f"Cut {i}",
            )
        )
    assert len(dedupe_cards(cards)) == 4
