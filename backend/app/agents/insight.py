from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from psycopg.types.json import Json

from ..config import get_settings
from ..db import insight_conn, jsonable_row, owner_conn
from ..llm import ChatMessage, generate, llm_available, text_of


def _bind(sql: str, params: tuple) -> str:
    out = sql
    for p in params:
        if isinstance(p, date):
            frag = f"DATE '{p.isoformat()}'"
        elif isinstance(p, (int, float)):
            frag = str(p)
        else:
            frag = "'" + str(p).replace("'", "''") + "'"
        out = out.replace("%s", frag, 1)
    return out


def _fetch(sql: str, params: tuple) -> tuple[list[dict], str]:
    bound = _bind(sql, params)
    with insight_conn() as conn:
        rows = [jsonable_row(r) for r in conn.execute(bound).fetchall()]
    return rows, bound


def _overdue(clock: date) -> list[dict]:
    sql = """
        SELECT po.purchase_order_id::text AS subject_key,
               po.purchase_order_id,
               s.supplier_name,
               po.expected_delivery_date,
               (%s - po.expected_delivery_date) AS days_overdue,
               COALESCE(SUM(pol.ordered_outers - pol.received_outers), 0) AS outstanding_outers
        FROM purchasing.purchase_orders po
        JOIN purchasing.suppliers s ON s.supplier_id = po.supplier_id
        LEFT JOIN purchasing.purchase_order_lines pol
          ON pol.purchase_order_id = po.purchase_order_id
        WHERE po.order_date <= %s
          AND po.expected_delivery_date < %s
          AND (po.is_order_finalized IS NOT TRUE
               OR pol.is_order_line_finalized IS NOT TRUE)
        GROUP BY po.purchase_order_id, s.supplier_name, po.expected_delivery_date
        ORDER BY days_overdue DESC
        LIMIT 10
    """
    rows, bound = _fetch(sql, (clock, clock, clock))
    return [
        {
            "rule_id": "overdue_purchase_orders",
            "category": "warning",
            "subject_key": r["subject_key"],
            "metrics": r,
            "source_tables": [
                "purchasing.purchase_orders",
                "purchasing.purchase_order_lines",
                "purchasing.suppliers",
            ],
            "sql_executed": bound,
            "template": (
                f"Purchase order {r['purchase_order_id']} from {r['supplier_name']} "
                f"is {int(r['days_overdue'])} days past its expected delivery."
            ),
        }
        for r in rows
    ]


def _sales_delta(clock: date, direction: str) -> list[dict]:
    t30 = clock - timedelta(days=29)
    p30s = clock - timedelta(days=59)
    p30e = clock - timedelta(days=30)
    if direction == "drop":
        pred = "t30 <= p30 * 0.6"
        rule_id = "unusual_sales_drop"
        category = "warning"
        label = "invoiced value fell"
    else:
        pred = "t30 >= p30 * 1.5"
        rule_id = "unusual_sales_rise"
        category = "positive"
        label = "invoiced value rose"
    sql = f"""
        WITH billed AS (
          SELECT c.customer_id, c.customer_name, i.invoice_date,
                 CASE WHEN i.is_credit_note THEN -il.extended_price ELSE il.extended_price END AS amt
          FROM sales.invoice_lines il
          JOIN sales.invoices i ON i.invoice_id = il.invoice_id
          JOIN sales.customers c ON c.customer_id = i.customer_id
          WHERE i.invoice_date <= %s
        )
        SELECT customer_id::text AS subject_key,
               customer_name,
               SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s) AS t30,
               SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s) AS p30
        FROM billed
        GROUP BY customer_id, customer_name
        HAVING SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s) >= 10000
           AND {pred}
        ORDER BY t30 / NULLIF(p30, 0)
        LIMIT 5
    """
    params = (clock, t30, clock, p30s, p30e, p30s, p30e)
    # HAVING uses t30/p30 aliases which PostgreSQL doesn't allow — rewrite with repeat
    sql = f"""
        WITH billed AS (
          SELECT c.customer_id, c.customer_name, i.invoice_date,
                 CASE WHEN i.is_credit_note THEN -il.extended_price ELSE il.extended_price END AS amt
          FROM sales.invoice_lines il
          JOIN sales.invoices i ON i.invoice_id = il.invoice_id
          JOIN sales.customers c ON c.customer_id = i.customer_id
          WHERE i.invoice_date <= %s
        ),
        agg AS (
          SELECT customer_id::text AS subject_key,
                 customer_name,
                 COALESCE(SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s), 0) AS t30,
                 COALESCE(SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s), 0) AS p30
          FROM billed
          GROUP BY customer_id, customer_name
        )
        SELECT * FROM agg
        WHERE p30 >= 10000 AND {pred}
        ORDER BY t30 / NULLIF(p30, 0)
        LIMIT 5
    """
    rows, bound = _fetch(sql, (clock, t30, clock, p30s, p30e))
    out = []
    for r in rows:
        pct = (float(r["t30"]) / float(r["p30"]) - 1) * 100 if r["p30"] else 0
        out.append(
            {
                "rule_id": rule_id,
                "category": category,
                "subject_key": f"customer:{r['subject_key']}",
                "metrics": r,
                "source_tables": ["sales.invoices", "sales.invoice_lines", "sales.customers"],
                "sql_executed": bound,
                "template": (
                    f"{r['customer_name']} {label} {abs(pct):.0f}% "
                    f"versus the prior 30 days."
                ),
            }
        )
    return out


def _quiet_customers(clock: date) -> list[dict]:
    sql = """
        WITH o AS (
          SELECT customer_id, order_date
          FROM sales.orders
          WHERE order_date <= %s
        ),
        last_ord AS (
          SELECT customer_id, MAX(order_date) AS last_order_date,
                 COUNT(*) FILTER (WHERE order_date BETWEEN %s AND %s) AS prior_90
          FROM o
          GROUP BY customer_id
        )
        SELECT l.customer_id::text AS subject_key,
               c.customer_name,
               l.last_order_date,
               l.prior_90,
               (%s - l.last_order_date) AS days_silent
        FROM last_ord l
        JOIN sales.customers c ON c.customer_id = l.customer_id
        WHERE l.prior_90 >= 3
          AND l.last_order_date < %s
        ORDER BY l.prior_90 DESC
        LIMIT 8
    """
    prior_start = clock - timedelta(days=135)
    prior_end = clock - timedelta(days=45)
    silent_since = clock - timedelta(days=45)
    rows, bound = _fetch(sql, (clock, prior_start, prior_end, clock, silent_since))
    return [
        {
            "rule_id": "customer_going_quiet",
            "category": "warning",
            "subject_key": r["subject_key"],
            "metrics": r,
            "source_tables": ["sales.orders", "sales.customers"],
            "sql_executed": bound,
            "template": (
                f"{r['customer_name']} has not ordered in {int(r['days_silent'])} days "
                f"after {int(r['prior_90'])} orders in the prior window."
            ),
        }
        for r in rows
    ]


def _region(clock: date) -> list[dict]:
    tq = date(clock.year, ((clock.month - 1) // 3) * 3 + 1, 1)
    lq_month = tq.month - 3
    lq_year = tq.year
    if lq_month <= 0:
        lq_month += 12
        lq_year -= 1
    lq = date(lq_year, lq_month, 1)
    lq_end = tq - timedelta(days=1)
    sql = """
        WITH billed AS (
          SELECT COALESCE(sp.sales_territory, co.country_name) AS region,
                 i.invoice_date,
                 CASE WHEN i.is_credit_note THEN -il.extended_price ELSE il.extended_price END AS amt
          FROM sales.invoice_lines il
          JOIN sales.invoices i ON i.invoice_id = il.invoice_id
          JOIN sales.customers c ON c.customer_id = i.customer_id
          JOIN application.cities ci ON ci.city_id = c.delivery_city_id
          JOIN application.state_provinces sp ON sp.state_province_id = ci.state_province_id
          JOIN application.countries co ON co.country_id = sp.country_id
          WHERE i.invoice_date <= %s
        ),
        agg AS (
          SELECT region,
                 COALESCE(SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s), 0) AS this_q,
                 COALESCE(SUM(amt) FILTER (WHERE invoice_date BETWEEN %s AND %s), 0) AS last_q
          FROM billed
          GROUP BY region
        )
        SELECT region AS subject_key, this_q, last_q,
               (this_q / NULLIF(last_q, 0) - 1) AS pct
        FROM agg
        WHERE last_q >= 20000
          AND (this_q >= last_q * 1.15 OR this_q <= last_q * 0.85)
        ORDER BY pct DESC
        LIMIT 6
    """
    rows, bound = _fetch(sql, (clock, tq, clock, lq, lq_end))
    out = []
    for r in rows:
        pct = float(r["pct"] or 0) * 100
        growth = pct >= 0
        out.append(
            {
                "rule_id": "region_growth" if growth else "region_loss",
                "category": "positive" if growth else "warning",
                "subject_key": r["subject_key"],
                "metrics": r,
                "source_tables": [
                    "sales.invoices",
                    "sales.invoice_lines",
                    "sales.customers",
                    "application.state_provinces",
                ],
                "sql_executed": bound,
                "template": (
                    f"{r['subject_key']} {'grew' if growth else 'declined'} "
                    f"{abs(pct):.0f}% this quarter versus last quarter."
                ),
            }
        )
    return out


def _spend_spike(clock: date) -> list[dict]:
    t30 = clock - timedelta(days=29)
    p30s = clock - timedelta(days=59)
    p30e = clock - timedelta(days=30)
    sql = """
        WITH lines AS (
          SELECT s.supplier_id, s.supplier_name, po.order_date,
                 pol.ordered_outers * pol.expected_unit_price_per_outer AS spend
          FROM purchasing.purchase_order_lines pol
          JOIN purchasing.purchase_orders po ON po.purchase_order_id = pol.purchase_order_id
          JOIN purchasing.suppliers s ON s.supplier_id = po.supplier_id
          WHERE po.order_date <= %s
        ),
        agg AS (
          SELECT supplier_id::text AS subject_key, supplier_name,
                 COALESCE(SUM(spend) FILTER (WHERE order_date BETWEEN %s AND %s), 0) AS t30,
                 COALESCE(SUM(spend) FILTER (WHERE order_date BETWEEN %s AND %s), 0) AS p30
          FROM lines
          GROUP BY supplier_id, supplier_name
        )
        SELECT * FROM agg
        WHERE p30 >= 5000 AND t30 >= p30 * 1.8
        ORDER BY t30 / NULLIF(p30, 0) DESC
        LIMIT 5
    """
    rows, bound = _fetch(sql, (clock, t30, clock, p30s, p30e))
    return [
        {
            "rule_id": "unusual_spend_spike",
            "category": "warning",
            "subject_key": r["subject_key"],
            "metrics": r,
            "source_tables": [
                "purchasing.purchase_orders",
                "purchasing.purchase_order_lines",
                "purchasing.suppliers",
            ],
            "sql_executed": bound,
            "template": (
                f"PO spend with {r['supplier_name']} is "
                f"{(float(r['t30']) / float(r['p30'])):.1f}× the prior 30 days."
            ),
        }
        for r in rows
    ]


def _concentration(clock: date) -> list[dict]:
    t90 = clock - timedelta(days=89)
    sql = """
        WITH lines AS (
          SELECT s.supplier_id, s.supplier_name,
                 pol.ordered_outers * pol.expected_unit_price_per_outer AS spend
          FROM purchasing.purchase_order_lines pol
          JOIN purchasing.purchase_orders po ON po.purchase_order_id = pol.purchase_order_id
          JOIN purchasing.suppliers s ON s.supplier_id = po.supplier_id
          WHERE po.order_date BETWEEN %s AND %s
        ),
        tot AS (SELECT SUM(spend) AS all_spend FROM lines)
        SELECT s.supplier_id::text AS subject_key, s.supplier_name,
               SUM(s.spend) AS supplier_spend, t.all_spend,
               SUM(s.spend) / NULLIF(t.all_spend, 0) AS share
        FROM lines s CROSS JOIN tot t
        GROUP BY s.supplier_id, s.supplier_name, t.all_spend
        HAVING SUM(s.spend) / NULLIF(t.all_spend, 0) >= 0.40
        ORDER BY share DESC
    """
    rows, bound = _fetch(sql, (t90, clock))
    return [
        {
            "rule_id": "supplier_concentration",
            "category": "warning",
            "subject_key": r["subject_key"],
            "metrics": r,
            "source_tables": [
                "purchasing.purchase_orders",
                "purchasing.purchase_order_lines",
                "purchasing.suppliers",
            ],
            "sql_executed": bound,
            "template": (
                f"{r['supplier_name']} is {float(r['share'])*100:.0f}% of trailing-90-day PO spend."
            ),
        }
        for r in rows
    ]


def _stockout(clock: date) -> list[dict]:
    t28 = clock - timedelta(days=27)
    sql = """
        WITH onhand AS (
          SELECT * FROM warehouse.on_hand_as_of(%s)
        ),
        demand AS (
          SELECT ol.stock_item_id, SUM(ol.quantity) / 28.0 AS daily_demand
          FROM sales.order_lines ol
          JOIN sales.orders o ON o.order_id = ol.order_id
          WHERE o.order_date BETWEEN %s AND %s
          GROUP BY ol.stock_item_id
          HAVING SUM(ol.quantity) > 0
        ),
        inbound AS (
          SELECT DISTINCT ON (pol.stock_item_id)
                 pol.stock_item_id,
                 po.purchase_order_id AS next_po_id,
                 po.expected_delivery_date AS next_po_date,
                 pol.ordered_outers * si.quantity_per_outer AS next_po_eaches
          FROM purchasing.purchase_order_lines pol
          JOIN purchasing.purchase_orders po ON po.purchase_order_id = pol.purchase_order_id
          JOIN warehouse.stock_items si ON si.stock_item_id = pol.stock_item_id
          WHERE po.order_date <= %s
            AND po.expected_delivery_date >= %s
            AND pol.is_order_line_finalized IS NOT TRUE
          ORDER BY pol.stock_item_id, po.expected_delivery_date
        )
        SELECT si.stock_item_id::text AS subject_key,
               si.stock_item_name,
               h.qty_on_hand,
               d.daily_demand,
               (h.qty_on_hand / NULLIF(d.daily_demand, 0)) AS days_of_cover,
               ib.next_po_id, ib.next_po_date, ib.next_po_eaches
        FROM demand d
        JOIN onhand h ON h.stock_item_id = d.stock_item_id
        JOIN warehouse.stock_items si ON si.stock_item_id = d.stock_item_id
        LEFT JOIN inbound ib ON ib.stock_item_id = d.stock_item_id
        WHERE h.qty_on_hand / NULLIF(d.daily_demand, 0) < 14
          AND (
            ib.next_po_date IS NULL
            OR ib.next_po_date > %s + (h.qty_on_hand / NULLIF(d.daily_demand, 0)) * INTERVAL '1 day'
          )
        ORDER BY days_of_cover ASC
        LIMIT 8
    """
    rows, bound = _fetch(sql, (clock, t28, clock, clock, clock, clock))
    out = []
    for r in rows:
        cover = float(r["days_of_cover"] or 0)
        out.append(
            {
                "rule_id": "stockout_projection",
                "category": "warning",
                "subject_key": r["subject_key"],
                "metrics": r,
                "source_tables": [
                    "warehouse.stock_item_holdings",
                    "warehouse.stock_item_transactions",
                    "purchasing.purchase_orders",
                    "sales.order_lines",
                ],
                "sql_executed": bound,
                "template": (
                    f"Stock for {r['stock_item_name']} covers about {cover:.0f} days "
                    f"at recent demand."
                ),
            }
        )
    return out


def _narrate(finding: dict, clock: date) -> str:
    if get_settings().insight_narrate.strip().lower() != "llm":
        return finding["template"]
    if not llm_available("agent"):
        return finding["template"]
    try:
        resp = generate(
            "You narrate a single already-confirmed insight. Do not add SKUs or change severity. "
            "One or two sentences, first person, calm. No alarmist words.",
            [
                ChatMessage(
                    role="user",
                    text=(
                        "Write the insight text for this finding as of "
                        + clock.isoformat()
                        + ":\n"
                        + json.dumps(
                            {"rule": finding["rule_id"], "metrics": finding["metrics"]},
                            default=str,
                        )
                    ),
                )
            ],
            role="agent",
        )
        text = text_of(resp)
        return text or finding["template"]
    except Exception:
        return finding["template"]


def refresh_alerts(clock: date) -> list[dict]:
    findings: list[dict] = []
    for fn in (
        _overdue,
        lambda c: _sales_delta(c, "drop"),
        lambda c: _sales_delta(c, "rise"),
        _quiet_customers,
        _region,
        _spend_spike,
        _concentration,
        _stockout,
    ):
        try:
            findings.extend(fn(clock))
        except Exception as exc:
            print(f"insight rule failed: {fn} {exc}", flush=True)

    # Cap ember so the UI stays calm: keep top 3 warnings + all positives
    warnings = [f for f in findings if f["category"] == "warning"][:1]
    positives = [f for f in findings if f["category"] == "positive"][:2]
    selected = warnings + positives

    from ..allowlists import display_names

    written = []
    with owner_conn() as conn:
        conn.execute(
            "DELETE FROM copilot.alerts WHERE as_of = %s AND resolved = false",
            (clock,),
        )
        for f in selected:
            text = _narrate(f, clock)
            aid = uuid.uuid4()
            conn.execute(
                """
                INSERT INTO copilot.alerts (
                  id, rule_id, category, text, metrics, source_tables, display_sources,
                  sql_executed, subject_key, as_of, resolved
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
                """,
                (
                    aid,
                    f["rule_id"],
                    f["category"],
                    text,
                    Json(f["metrics"]),
                    f["source_tables"],
                    display_names(f["source_tables"]),
                    f["sql_executed"],
                    f["subject_key"],
                    clock,
                ),
            )
            written.append(
                {
                    "id": str(aid),
                    "rule_id": f["rule_id"],
                    "category": f["category"],
                    "text": text,
                    "metrics": f["metrics"],
                    "source_tables": f["source_tables"],
                    "display_sources": display_names(f["source_tables"]),
                    "sql_executed": f["sql_executed"],
                    "subject_key": f["subject_key"],
                    "as_of": clock.isoformat(),
                }
            )
    return written


def list_alerts(clock: date) -> list[dict]:
    with owner_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, rule_id, category, text, metrics, source_tables, display_sources,
                   sql_executed, subject_key, created_at, as_of
            FROM copilot.alerts
            WHERE as_of = %s AND resolved = false
            ORDER BY category DESC, created_at
            """,
            (clock,),
        ).fetchall()
    out = []
    for r in rows:
        item = jsonable_row(r)
        item["id"] = str(item["id"])
        out.append(item)
    return out
