# Data README — what you can ask

Zo-Pro Copilot answers **unscripted questions about sales, purchasing, stock, and a handful of clock facts** from a **read-only slice** of Wide World Importers (WWI) on Postgres. It is not a general company brain. If the answer is not in these tables, as of the demo clock, the product should refuse rather than invent.

This file is the question catalog and the boundary. Schema columns live in the allow-list docs. How data is loaded lives in [`data-setup.md`](data-setup.md). How to judge a demo lives in [`evaluation.md`](evaluation.md). Example utterances here are **capability coverage**, not a hardcoded script.

## What the database is

WWI is a wholesale novelty-goods company. The MVP copies an allow-listed subset of the SQL Server OLTP Full backup into Postgres.

| | |
|---|---|
| Seeded transactional dates | **2013-01-01 → 2016-05-31** |
| Demo clock (default “today”) | **2015-09-14** |
| Fiscal year | Calendar year. Q1 = Jan–Mar. Default clock → **FY2015 Q3** |
| Access | `SELECT` only. No writes to company tables |

“Today”, “last month”, and “this quarter” resolve against the **demo clock**, not the real calendar. Wall-clock “this week in 2026” returns nothing.

---

## Question types that work

Questions are not a menu. The copilot generates SQL on demand. These six bands are what the data can actually support.

### 1. Clock / “what period are we in?”

Date, fiscal year, quarter, month **as of the demo clock**.

Answered from the clock with **no LLM and no SQL**. “How did last quarter look?” is **not** this band — that is a metric question.

### 2. Sales performance (money in)

Invoiced revenue, booked orders, profit, mix, rankings, comparisons vs a prior period.

Grain that matters:

- **Earned / revenue / “how did we perform”** → `sales.invoices` + `sales.invoice_lines` (`extended_price`; credit notes handled)
- **Booked / pipeline / order volume** → `sales.orders` + `sales.order_lines` (`quantity × unit_price`)
- **Profit** → `sales.invoice_lines.line_profit` (not PO spend, not tax)

### 3. Customers, products, people, geography

Who bought, who went quiet, top accounts/SKUs, salesperson, region / country / territory growth.

Region is **delivery city → state/province → country** (or `sales_territory` when present). It is not a separate region fact table. People are salespeople and contacts, **not** customers. Customers live in `sales.customers`.

### 4. Purchasing and stock (money out / ops)

Suppliers, PO spend, overdue receipts, lead time, on-hand as of clock, reorder policy, inbound vs demand.

On-hand is **reconstructed**: end-of-backup holdings minus movements after the clock. Raw `warehouse.stock_item_holdings.quantity_on_hand` is only valid if the clock is **2016-05-31**. PO quantities are **outers** (packs), not eaches — convert with `warehouse.stock_items.quantity_per_outer`.

### 5. Cross-domain (needs both sides)

Margin, buy vs sell, cost vs price, “are we buying enough for what’s selling,” next-period suggestion from trailing sales **and** cost.

Sales cannot read purchasing. Purchase cannot read sales. These questions go through both agents or a special cross-domain `SELECT`.

### 6. “What needs attention?”

Live insight cards from a **fixed rule catalog** (stockout risk, overdue POs, sales drop, quiet customers, margin compression, spend spikes, supplier concentration, demand vs inbound, plus a few positives). See [`insight-rules.md`](insight-rules.md).

The copilot **reads alerts**. It does not invent a new concern mid-chat.

Forward-looking questions (“how might next quarter look?”) are a **disclosed run-rate / same-quarter-last-year suggestion**, not a forecast model.

---

## Boundary limits

Four walls: **data**, **time**, **privilege**, and **product behavior**.

### Data wall — only these tables exist

| Domain | What’s in | What’s not |
|---|---|---|
| Sales | customers, categories, buying groups, orders/lines, invoices/lines, customer transactions | Quotes, CRM notes, marketing, returns as a separate process beyond credit notes |
| Purchasing | suppliers, categories, POs/lines, supplier transactions | Contracts, RFQs, freight invoices as a first-class object |
| Warehouse | stock items, holdings (policy + end snapshot), transactions, groups, colors, packages | Vehicles, cold rooms, warehouse telemetry |
| Application | people, cities/states/countries, delivery & payment methods, transaction types | Passwords, photos, website schema, sequences, system params |

**Not migrated at all:** `Website.*`, HR/payroll, GL/accounting beyond AR/AP transaction rows, manufacturing, support tickets, emails, user permissions, anything after mid-2016.

Also skipped from columns: photos, hashed passwords, search blobs, geography types, comments/tags.

Allow-lists and joins: [`schema-sales.md`](schema-sales.md), [`schema-purchasing.md`](schema-purchasing.md), [`schema-warehouse.md`](schema-warehouse.md), [`schema-application.md`](schema-application.md).

### Time wall

- Inclusive cutoff: dates **after** the clock are ignored; the clock day is included.
- Relative language (“last month”, “this quarter”, “YTD”) resolves against the **clock**, not the OS date.
- Dimensions (customer names, SKUs, cities) are current rows, not slowly-changing history.
- Ask with the clock in 2015 / early 2016 or you get empty periods.

Dated columns for the cutoff: `sales.orders.order_date`, `sales.invoices.invoice_date`, `sales.customer_transactions.transaction_date`, `purchasing.purchase_orders.order_date`, `purchasing.supplier_transactions.transaction_date`, `warehouse.stock_item_transactions.transaction_occurred_when`.

### Privilege / query wall

- **SELECT only.** No writes to company data.
- Tables must be qualified as `schema.table` and on that agent’s allow-list.
- **Row cap 500**, **5s timeout** (insight 15s). Rankings and “how did we perform” need aggregates, not a dump of every invoice.
- One statement. No `INSERT` / `UPDATE` / `DROP` / etc.

Sales **cannot** read `purchasing.*` or warehouse holdings/transactions. Purchase **cannot** read `sales.*`. Margin-style questions need both agents or `cross_domain_query`.

### Product-behavior wall

| You can | You cannot |
|---|---|
| Ask any sales/purchasing question in plain language | Get a hardcoded FAQ — metrics are computed |
| Follow up on the last answer / open data tab | Persist chats across sessions, or log in as a specific user |
| Click a card and inspect rows + SQL | Change, approve, or create orders/POs |
| Ask “what needs attention?” and get rule-backed cards | Get freeform “what looks concerning” beyond the rule catalog |
| Get a next-quarter **suggestion** with named metrics | Get a true ML forecast or a guaranteed outlook |
| Get clock/FY answers even if the LLM is down | Get HR, legal, poems, unmigrated schema, or invented numbers when SQL returns `no_data` |

WWI-specific gotchas that look like product limits:

- PO quantities are **outers**, not eaches.
- Credit notes must be excluded or subtracted from revenue.
- “People” are not customers.

---

## Example questions a business owner asks

These are the kind of things a GM / owner would type. They are **not** product scripts. Paraphrase freely.

### Morning check-in

- What’s today’s date on this dashboard?
- Which quarter / financial year are we in?
- What needs attention right now?
- How did we do last month?
- How did last quarter look compared with the quarter before?

### Money in

- How much did we invoice year to date?
- Show monthly earnings for the last six months.
- What’s our profit this quarter?
- Booked vs invoiced this month — are we converting orders?
- Which products made the most money last quarter?
- Which salesperson is carrying the most orders this month?

### Customers

- Who are our top 10 customers this quarter?
- Which customers dropped off this month vs last month?
- Who used to order regularly and has gone quiet?
- What’s Tailspin Toys (or another buying group) doing vs last quarter?
- Are any accounts on credit hold, and what’s outstanding?

### Geography

- Which territory grew this quarter?
- Which country shrank vs last quarter?
- Compare sales in the United States vs whatever other countries we actually ship to.

### Products / mix

- What’s selling well right now?
- Did mix shift from units to revenue — are we selling fewer expensive items?
- Which SKUs had the biggest unit drop in the last 30 days?

### Buying / suppliers

- How much did we commit on POs last month?
- Who are we spending the most with this quarter?
- Which purchase orders are overdue?
- Which suppliers are slow against expected delivery?
- What’s typical lead time on our top SKUs?

### Stock / ops

- What is at risk of stocking out in the next two weeks?
- Are we buying enough given recent demand?
- What’s on hand for USB food flash drives (or any named SKU) as of today?
- Did we undersize the reorder on that item?

### Margin (both sides of the business)

- Which products have the thinnest margin right now?
- Where did cost go up while selling price stayed flat?
- Are we still making money on our best sellers after inbound cost?

### Looking ahead (suggestion only — not a forecast)

- Based on the last 90 days, how should we think about next quarter?
- If we run at the same pace as last quarter, what does next quarter look like?
- How does this quarter compare with the same quarter last year?

### Follow-ups (after a card or chart is open)

- Why that SKU?
- Break that down by customer.
- Show me the last 10 invoices for that account.
- Is that drop real, or is it credit notes?

---

## Questions this product cannot answer

Useful as a boundary test:

- What’s our cash in the bank / P&L / tax position? *(no GL)*
- What’s our headcount, payroll, or overtime? *(no HR)*
- Why did that customer complain / what’s in the emails? *(no CRM/support)*
- Raise a PO / hold this customer / change a price. *(read-only)*
- Will next quarter definitely hit $X? *(no predictive model)*
- How’s the website converting? *(Website schema not migrated)*
- Compare us to competitors or market share. *(only this company’s tables)*
- What’s happening this week in 2026? *(data ends May 2016; clock must sit inside 2013–2016)*

**Short version:** a general owner can ask **how the wholesale business is performing, who is buying, who we buy from, what’s in stock, what’s late, what’s thinning on margin, and what the rules already flagged** — as of the demo clock, from those tables only. Everything else is out of bounds.
