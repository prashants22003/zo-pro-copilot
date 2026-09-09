# Insight rules — Zo-Pro Copilot

Deterministic catalog. A rule **fires or it does not**. Card text is the rule template by default; optional LLM narration (`INSIGHT_NARRATE=llm`) only rewrites rows already flagged. No freeform “what looks concerning.”

All rules use the **demo clock** as “today.” Transactional filters: date ≤ clock.

After first seed, run the verification checklist at the bottom and tune thresholds if nothing (or everything) fires. Thresholds below are starting points, not sacred.

## Shared helpers

### On-hand as of clock

`holdings.quantity_on_hand` at data-end minus `SUM(stock_item_transactions.quantity)` where `transaction_occurred_when::date > clock`. See `docs/schema-warehouse.md`. Do not sum all transactions as if stock started at zero.

### Trailing demand (units)

From `sales.order_lines` joined to `sales.orders` (or invoice lines if we standardize on earned units — **lock to order_lines for stockout demand**):

`SUM(quantity)` for the last 28 days ending on clock, for that `stock_item_id`. Daily rate = that sum / 28. If 28-day volume is 0, skip stockout (do not divide by zero).

### Next inbound

Open `purchasing.purchase_order_lines` (not finalized) joined to POs with `expected_delivery_date >= clock`, earliest date, quantity in **eaches** (`ordered_outers * quantity_per_outer`).

### Period windows

Clock-relative: this month, last month, this quarter, last quarter, trailing 90 days vs prior 90 days. Same definitions as `docs/schema-sales.md`.

### Projection helper (not an alert)

Used when the user asks how the next month/quarter may look. Not written to `copilot.alerts` unless a separate rule fired.

- **Run-rate:** last 90 days revenue (invoices, ex credit notes) × (days in next period / 90)
- **Seasonal-naive:** same quarter last year, if `clock - 1 year` still falls inside the dataset
- Return both numbers plus `metrics_used`. Orchestrator presents them as a **suggestion**.

## Alert row shape

Written to `copilot.alerts` (see `docs/api.md`). `category` is `warning` | `positive`. `rule_id` is stable (below). Re-running rules for a clock **replaces** unresolved alerts for that clock (delete+insert or upsert on `(rule_id, subject_key, as_of)`).

---

## Warning rules

### `stockout_projection`

| | |
|---|---|
| Category | warning |
| Subject | `stock_item_id` |
| Tables | Warehouse.StockItemTransactions, Purchasing.PurchaseOrders, Purchasing.PurchaseOrderLines, Warehouse.StockItems, Sales.OrderLines, Sales.Orders |
| Fires when | `days_of_cover = qty_on_hand / daily_demand < 14` **and** (no inbound before stockout **or** inbound date > clock + days_of_cover) |
| Metrics | `qty_on_hand`, `daily_demand`, `days_of_cover`, `next_po_id`, `next_po_date`, `next_po_eaches` |
| Cap | Top 8 SKUs by soonest stockout |

### `overdue_purchase_orders`

| | |
|---|---|
| Category | warning |
| Subject | `purchase_order_id` |
| Tables | Purchasing.PurchaseOrders, PurchaseOrderLines, Suppliers |
| Fires when | `expected_delivery_date < clock` AND (`is_order_finalized` is false OR any line `is_order_line_finalized` is false) |
| Metrics | days overdue, supplier, outstanding outers |
| Cap | Top 10 by days overdue |

### `unusual_sales_drop`

| | |
|---|---|
| Category | warning |
| Subject | customer **or** stock item **or** sales territory (run three grains; each has own `subject_key`) |
| Tables | Sales.Invoices, InvoiceLines, Customers, StockItems, Application.StateProvinces |
| Fires when | trailing 30d invoiced `extended_price` (ex credits) is **≤ 60%** of the prior 30d, and prior 30d ≥ a floor (e.g. 10,000) so noise accounts drop out |
| Metrics | t30, p30, pct_change, grain |
| Cap | Top 5 per grain |

### `customer_going_quiet`

| | |
|---|---|
| Category | warning |
| Subject | `customer_id` |
| Tables | Sales.Orders, Sales.Customers |
| Fires when | customer had ≥ 3 orders in the 90 days **before** the last 45 days, and **zero** orders in the last 45 days (all ≤ clock) |
| Metrics | last_order_date, orders_in_prior_90, days_silent |
| Cap | Top 8 by historical order value |

### `margin_compression`

| | |
|---|---|
| Category | warning |
| Subject | `stock_item_id` |
| Tables | Sales.InvoiceLines, Invoices, Purchasing.PurchaseOrderLines, PurchaseOrders, Warehouse.StockItems |
| Fires when | average selling `unit_price` (invoices, last 90d) minus average inbound cost per each (POs last 90d, price per outer / `quantity_per_outer`) is **< 70%** of the same margin in the prior 90d, or margin **< 0** |
| Metrics | sell_avg, cost_avg, margin, margin_prior, pct_of_prior |
| Cap | Top 8 by worst margin delta |
| Note | Needs `cross_domain` / insight role. Skip SKUs missing cost or price. |

### `unusual_spend_spike`

| | |
|---|---|
| Category | warning |
| Subject | `supplier_id` or `stock_item_id` |
| Tables | Purchasing.PurchaseOrders, PurchaseOrderLines, Suppliers |
| Fires when | last 30d PO spend ≥ **1.8×** prior 30d and prior 30d ≥ a floor |
| Metrics | t30_spend, p30_spend, ratio |
| Cap | Top 5 |

### `supplier_concentration`

| | |
|---|---|
| Category | warning |
| Subject | `supplier_id` |
| Tables | PurchaseOrderLines, PurchaseOrders, Suppliers, StockItems |
| Fires when | one supplier is **≥ 40%** of trailing 90d PO spend |
| Metrics | supplier_spend, total_spend, share |
| Cap | All who breach (usually few) |

### `demand_vs_inbound_mismatch`

| | |
|---|---|
| Category | warning |
| Subject | `stock_item_id` |
| Tables | OrderLines, Orders, PurchaseOrderLines, PurchaseOrders, StockItems |
| Fires when | trailing 28d unit demand **> 1.5×** eaches due in the next 28d (open POs) **and** days of cover < 21 |
| Metrics | demand_28, inbound_28, days_of_cover |
| Cap | Top 8 |

---

## Positive rules

At least one positive finding should fire on a well-chosen clock so the demo is not only ember.

### `unusual_sales_rise`

| | |
|---|---|
| Category | positive |
| Subject | customer or stock item |
| Tables | Sales.Invoices, InvoiceLines, Customers, StockItems |
| Fires when | trailing 30d invoiced value ≥ **1.5×** prior 30d and prior 30d ≥ floor |
| Cap | Top 5 |

### `region_growth`

| | |
|---|---|
| Category | positive |
| Subject | `sales_territory` or country |
| Tables | Invoices, Customers, Cities, StateProvinces, Countries |
| Fires when | this quarter-to-date vs last full quarter: value **≥ +15%** and last quarter ≥ floor |
| Cap | Top 3 territories |
| Sibling | `region_loss` (warning): **≤ −15%**, same floors — include as `region_loss` |

### `on_time_supplier`

| | |
|---|---|
| Category | positive |
| Subject | `supplier_id` |
| Tables | PurchaseOrders, PurchaseOrderLines, Suppliers |
| Fires when | among suppliers with ≥ 5 POs in trailing 90d, **≥ 90%** have `expected_delivery_date` ≤ receipt (`last_receipt_date`) or finalized without overdue |
| Cap | Top 3 |
| Note | If receipt dates are too sparse after migrate, drop this rule rather than fake it. |

---

## Narration layer

Input: fired rule id, metrics JSON, 5–20 subject rows.  
Output: `text` (Inter-length, one or two sentences), label already determined by category.  
Forbidden: adding SKUs that were not in the payload; changing category; using ember language for `positive`.

## Orchestrator use

On load and on clock change: run rule layer → narrate new/changed fires → upsert `copilot.alerts` → `get_live_alerts` → insight cards.

User question “what needs attention?” **reads alerts**, it does not invent a new catalog.

## Verification (do this once after seed)

For default clock `2015-09-14` (or the date you lock):

- [ ] At least one `warning` and one `positive` fire
- [ ] `stockout_projection` either fires with inspectable SQL or we document “no SKU at risk at this clock” and pick another clock
- [ ] No rule returns hundreds of cards (caps hold)
- [ ] Changing clock to data-min silences late-period rules
- [ ] Holdings vs transactions: on-hand at data-end matches holdings within a small tolerance

Record the locked clock and which rules fired in `docs/decisions.md` after that pass.
