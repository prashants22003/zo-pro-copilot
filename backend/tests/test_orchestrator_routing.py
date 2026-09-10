from datetime import date

from app.llm import GenerateResult, ToolCall, orchestrator_tools
from app.agents.orchestrator import opening_status, run_chat

CLOCK = date(2015, 9, 14)

SALES_RESULT = {
    "rows": [{"line_profit": 1_200_000.0}],
    "sql_executed": [
        "SELECT SUM(il.line_profit) AS line_profit FROM sales.invoice_lines il "
        "JOIN sales.invoices i ON i.invoice_id = il.invoice_id "
        "WHERE i.invoice_date BETWEEN DATE '2015-03-01' AND DATE '2015-03-31'"
    ],
    "source_tables": ["sales.invoice_lines", "sales.invoices"],
    "display_sources": ["Sales.InvoiceLines", "Sales.Invoices"],
    "metrics_used": ["line_profit"],
    "confidence": "ok",
}

PURCHASE_RESULT = {
    "rows": [{"days_overdue": 12}],
    "sql_executed": [
        "SELECT po.purchase_order_id, (%s) FROM purchasing.purchase_orders po "
        "WHERE po.expected_delivery_date < DATE '2015-09-14'"
    ],
    "source_tables": ["purchasing.purchase_orders"],
    "display_sources": ["Purchasing.PurchaseOrders"],
    "metrics_used": [],
    "confidence": "ok",
}


def _patch_clock_and_llm(monkeypatch, generate_fn, domain_fn=None, alerts=None):
    monkeypatch.setattr("app.agents.orchestrator.get_clock", lambda: CLOCK)
    monkeypatch.setattr("app.agents.orchestrator.llm_available", lambda role=None: True)
    monkeypatch.setattr("app.agents.orchestrator.generate", generate_fn)
    if domain_fn:
        monkeypatch.setattr("app.agents.orchestrator.run_domain_agent", domain_fn)
    if alerts is not None:
        monkeypatch.setattr("app.agents.orchestrator.list_alerts", lambda clock: alerts)


def test_orchestrator_tools_have_no_execute_sql() -> None:
    names = {t.name for t in orchestrator_tools()}
    assert names == {"sales_agent", "purchase_agent", "get_live_alerts", "cross_domain_query"}
    assert "execute_sql" not in names


def test_profit_routes_to_sales_agent(monkeypatch) -> None:
    seen = []

    def fake_generate(system, messages, tools=None, role="orchestrator"):
        if tools:
            return GenerateResult(
                text="",
                tool_calls=[ToolCall(name="sales_agent", args={"question": "March 2015 profit"})],
            )
        return GenerateResult(text="Line profit for March 2015 was 1,200,000.")

    def fake_domain(*, domain, question, context, clock):
        seen.append(domain)
        assert domain == "sales"
        assert "line_profit" in question
        return dict(SALES_RESULT)

    _patch_clock_and_llm(monkeypatch, fake_generate, fake_domain)
    out = run_chat("how much profit we made in march 2015?", [])
    assert seen == ["sales"]
    assert "1,200,000" in out["answer"] or "1,200,000" in str(out["cards"])
    assert "execute_sql" not in out["answer"]
    assert "SELECT" not in out["answer"]
    assert len(out["cards"]) == 1
    assert out["cards"][0]["title"] == "Line profit"


def test_overdue_routes_to_purchase_agent(monkeypatch) -> None:
    seen = []

    def fake_generate(system, messages, tools=None, role="orchestrator"):
        if tools:
            return GenerateResult(
                text="",
                tool_calls=[
                    ToolCall(name="purchase_agent", args={"question": "overdue purchase orders"})
                ],
            )
        return GenerateResult(text="There are overdue purchase orders on the books.")

    def fake_domain(*, domain, question, context, clock):
        seen.append(domain)
        return dict(PURCHASE_RESULT)

    _patch_clock_and_llm(monkeypatch, fake_generate, fake_domain)
    out = run_chat("Show overdue purchase orders", [])
    assert seen == ["purchase"]
    assert len(out["cards"]) == 1


def test_attention_routes_to_alerts(monkeypatch) -> None:
    def fake_generate(system, messages, tools=None, role="orchestrator"):
        if tools:
            return GenerateResult(text="", tool_calls=[ToolCall(name="get_live_alerts", args={})])
        return GenerateResult(text="One supplier delivery is slipping.")

    alerts = [
        {
            "id": "a1",
            "category": "warning",
            "text": "PO 12 is overdue.",
            "metrics": {"days_overdue": 9},
            "display_sources": ["Purchasing.PurchaseOrders"],
            "sql_executed": "SELECT 1",
            "subject_key": "12",
        }
    ]
    _patch_clock_and_llm(monkeypatch, fake_generate, alerts=alerts)
    out = run_chat("what needs attention?", [])
    assert len(out["cards"]) == 1
    assert out["cards"][0]["title"] == "Needs attention"


def test_leaked_json_uses_template(monkeypatch) -> None:
    def fake_generate(system, messages, tools=None, role="orchestrator"):
        if tools:
            return GenerateResult(
                text="",
                tool_calls=[ToolCall(name="sales_agent", args={"question": "profit"})],
            )
        return GenerateResult(
            text='{"name": "execute_sql", "arguments": {"query": "SELECT 1"}}'
        )

    _patch_clock_and_llm(monkeypatch, fake_generate, lambda **k: dict(SALES_RESULT))
    out = run_chat("how much profit in march 2015?", [])
    assert "execute_sql" not in out["answer"]
    assert "SELECT" not in out["answer"]
    assert "line_profit" in out["answer"].lower() or "Line profit" in out["answer"] or "profit" in out["answer"].lower()
    assert "Sales.InvoiceLines" not in out["answer"]


def test_opening_status_names_the_domain() -> None:
    assert "sales" in opening_status("how much profit we made in march 2015?").lower()
    assert "purchasing" in opening_status("Show overdue purchase orders").lower()
    assert "attention" in opening_status("what needs attention?").lower()


def test_on_status_reports_routing(monkeypatch) -> None:
    notes: list[str] = []

    def fake_generate(system, messages, tools=None, role="orchestrator"):
        if tools:
            return GenerateResult(
                text="",
                tool_calls=[ToolCall(name="sales_agent", args={"question": "profit"})],
            )
        return GenerateResult(text="March line profit came to 1,200,000.")

    _patch_clock_and_llm(monkeypatch, fake_generate, lambda **k: dict(SALES_RESULT))
    run_chat("how much profit we made in march 2015?", [], on_status=notes.append)
    joined = " ".join(notes).lower()
    assert "sales" in joined
    assert "short answer" in joined


def test_fallback_skips_second_orchestrator_call(monkeypatch) -> None:
    n = {"c": 0}

    def fake_generate(system, messages, tools=None, role="orchestrator"):
        n["c"] += 1
        return GenerateResult(text="no native tools")

    _patch_clock_and_llm(monkeypatch, fake_generate, lambda **k: dict(SALES_RESULT))
    out = run_chat("how much profit we made in march 2015?", [])
    assert n["c"] == 1
    assert len(out["cards"]) == 1
    assert "execute_sql" not in out["answer"]


def test_native_calls_request_synthesis(monkeypatch) -> None:
    n = {"c": 0}

    def fake_generate(system, messages, tools=None, role="orchestrator"):
        n["c"] += 1
        if tools:
            return GenerateResult(
                text="",
                tool_calls=[
                    ToolCall(
                        name="sales_agent",
                        args={"question": "profit"},
                        thought_signature=b"sig",
                    )
                ],
                model_parts=[
                    {
                        "function_call": {"name": "sales_agent", "args": {"question": "profit"}},
                        "thought_signature": b"sig",
                    }
                ],
            )
        return GenerateResult(text="Line profit for March 2015 was 1,200,000.")

    _patch_clock_and_llm(monkeypatch, fake_generate, lambda **k: dict(SALES_RESULT))
    out = run_chat("how much profit we made in march 2015?", [])
    assert n["c"] == 2
    assert "1,200,000" in out["answer"]

