from __future__ import annotations

import re

from .allowlists import PURCHASE_TABLES, SALES_TABLES

_WS = re.compile(r"\s+")

METRICS: list[dict] = [
    {
        "id": "profit",
        "title": "Line profit",
        "domain": "sales",
        "keywords": (
            r"\bprofits?\b",
            r"how much (did we|we) make",
            r"\bmade\b.{0,24}\bmoney\b",
        ),
        "required_prefixes": ("sales.",),
        "forbidden_prefixes": ("purchasing.",),
        "required_tables": ("sales.invoice_lines",),
        "brief": (
            "Compute profit as SUM(line_profit) from sales.invoice_lines "
            "joined to sales.invoices. Filter invoice_date to the asked period "
            "and invoice_date <= the demo clock. Handle is_credit_note "
            "(subtract or negate credit-note lines). "
            "Do not use purchasing.supplier_transactions, tax_amount, or PO spend. "
            "Cite Sales.InvoiceLines."
        ),
    },
    {
        "id": "revenue",
        "title": "Invoiced revenue",
        "domain": "sales",
        "keywords": (
            r"\brevenue\b",
            r"\binvoiced\b",
            r"money in",
            r"how did we perform",
            r"\bearnings?\b",
            r"how did .{0,20}(month|quarter|year)",
        ),
        "required_prefixes": ("sales.",),
        "forbidden_prefixes": ("purchasing.",),
        "required_tables": (),
        "brief": (
            "Revenue (invoiced) is SUM of sales.invoice_lines.extended_price joined to "
            "sales.invoices, excluding or negating is_credit_note. "
            "Filter invoice_date to the asked period and <= the demo clock. "
            "Booked value is order_lines.quantity * unit_price only if they asked about orders."
        ),
    },
    {
        "id": "spend",
        "title": "Purchase spend",
        "domain": "purchase",
        "keywords": (
            r"\bspend\b",
            r"\bpurchase orders?\b",
            r"\boverdue\b",
            r"\bsuppliers?\b",
            r"money out",
            r"\bpo\b",
        ),
        "required_prefixes": ("purchasing.",),
        "forbidden_prefixes": tuple(sorted(SALES_TABLES - PURCHASE_TABLES)),
        "required_tables": (),
        "brief": (
            "Use purchasing.purchase_orders / purchase_order_lines / suppliers. "
            "PO spend is ordered_outers * expected_unit_price_per_outer. "
            "Filter order_date <= the demo clock. Do not query sales invoices for spend."
        ),
    },
    {
        "id": "margin",
        "title": "Margin",
        "domain": "both",
        "keywords": (r"\bmargin\b", r"buy vs sell", r"thinnest margin", r"cost vs price"),
        "required_prefixes": (),
        "forbidden_prefixes": (),
        "required_tables": (),
        "brief": (
            "Need selling price from sales invoice/order lines and inbound cost from "
            "purchasing PO lines (price per outer / quantity_per_outer). Split the work "
            "across sales_agent and purchase_agent, or use cross_domain_query for a real join."
        ),
    },
]


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def metrics_prompt() -> str:
    lines = [
        "Metric contract (follow this when briefing agents):",
        "- profit → Sales only. SUM(line_profit) on sales.invoice_lines ⋈ sales.invoices.",
        "- revenue / how did we perform → Sales. invoiced extended_price, credit notes handled.",
        "- spend / overdue POs / suppliers → Purchase.",
        "- margin / buy vs sell → both agents (or cross_domain_query).",
        "Never treat purchasing.supplier_transactions as profit.",
    ]
    return "\n".join(lines)


def match_metric(question: str) -> dict | None:
    text = _norm(question)
    if not text:
        return None
    for metric in METRICS:
        for pat in metric["keywords"]:
            if re.search(pat, text, re.I):
                return metric
    return None


def compose_brief(question: str, metric: dict | None, *, retry: bool = False) -> str:
    parts = [(question or "").strip() or "Answer the user's question from this domain."]
    if metric:
        parts.append(str(metric["brief"]))
    if retry and metric:
        parts.append(
            "The previous query used the wrong tables for this metric. "
            "Follow the brief exactly and stay on this domain's allow-list."
        )
    return "\n".join(parts)


def sources_match_contract(tables: list[str] | None, metric: dict | None) -> bool:
    if not metric:
        return True
    tset = {str(t).lower() for t in (tables or []) if t}
    if not tset:
        return False
    if metric["id"] in {"profit", "revenue"}:
        if any(t.startswith("purchasing.") for t in tset):
            return False
        if not any(t.startswith("sales.") for t in tset):
            return False
        if metric["id"] == "profit" and "sales.invoice_lines" not in tset:
            return False
        return True
    if metric["id"] == "spend":
        sales_only = tset & (SALES_TABLES - PURCHASE_TABLES)
        if sales_only:
            return False
        return any(t.startswith("purchasing.") for t in tset)
    return True


def _spoken_label(raw: str | None, title: str | None) -> str:
    text = (raw or title or "the figure").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "The figure"


def template_from_kpis(
    kpis: list[dict],
    sources: list[str],
    *,
    title: str | None = None,
    clock: str | None = None,
) -> str:
    del sources  # cards already cite sources; spoken answers should not name tables
    if not kpis:
        return "I could not get a clean number for that from the live data."
    head = kpis[0]
    value = head.get("value")
    label = _spoken_label(head.get("label"), title)
    as_of = f" That's as of the demo clock ({clock})." if clock else ""
    extra = ""
    if len(kpis) > 1:
        rest = "; ".join(
            f"{_spoken_label(k.get('label'), None)} {k.get('value')}" for k in kpis[1:3]
        )
        extra = f" Also worth noting: {rest}."
    return (
        f"{label} comes to {value}.{as_of}{extra} "
        "Open a card if you want the rows behind it."
    ).strip()
