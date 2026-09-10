from app.metrics import compose_brief, match_metric, sources_match_contract, template_from_kpis


def test_profit_maps_to_sales_line_profit() -> None:
    metric = match_metric("how much profit we made in march 2015?")
    assert metric is not None
    assert metric["id"] == "profit"
    assert metric["domain"] == "sales"
    brief = compose_brief("March 2015 profit", metric)
    assert "line_profit" in brief
    assert "invoice_lines" in brief


def test_purchasing_sources_rejected_for_profit() -> None:
    metric = match_metric("profit")
    assert not sources_match_contract(["purchasing.supplier_transactions"], metric)
    assert sources_match_contract(["sales.invoice_lines", "sales.invoices"], metric)


def test_revenue_rejects_purchasing() -> None:
    metric = match_metric("what was our revenue last month")
    assert metric["id"] == "revenue"
    assert not sources_match_contract(["purchasing.purchase_orders"], metric)


def test_spend_rejects_sales_invoices() -> None:
    metric = match_metric("supplier spend last month")
    assert metric["id"] == "spend"
    assert not sources_match_contract(["sales.invoices"], metric)
    assert sources_match_contract(["purchasing.purchase_orders"], metric)


def test_empty_sources_fail_contract() -> None:
    metric = match_metric("profit")
    assert not sources_match_contract([], metric)
    assert sources_match_contract(None, None)


def test_template_from_kpis_speaks_like_a_person() -> None:
    text = template_from_kpis(
        [{"value": "1,200,000", "label": "line profit"}],
        ["Sales.InvoiceLines", "Sales.Invoices"],
        title="Line profit",
        clock="2015-09-14",
    )
    assert "1,200,000" in text
    assert "profit" in text.lower()
    assert "comes to" in text
    assert "Sales.InvoiceLines" not in text
    assert "queried tables" not in text
    assert "2015-09-14" in text
