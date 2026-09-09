# Schema — Sales allow-list

Physical names (Postgres) first. Display name in parentheses for the UI.

Clock cutoff: `order_date` / `invoice_date` / `transaction_date` ≤ demo clock. See `docs/data-setup.md`.

## Look here first

| Question about… | Start here |
|---|---|
| Money **earned** (invoiced) | `sales.invoices` + `sales.invoice_lines` |
| Orders **booked** / pipeline | `sales.orders` + `sales.order_lines` |
| Who the customer is | `sales.customers` |
| Region / country / state | `customers.delivery_city_id` → `application.cities` → `state_provinces` → `countries` |
| Product sold | `order_lines` / `invoice_lines`.`stock_item_id` → `warehouse.stock_items` |
| Salesperson | `orders.salesperson_person_id` → `application.people` |
| Quiet / declining customer | Compare invoiced or ordered value this period vs prior (clock-relative) |

Prefer **invoices** for “money earned / how did we perform”. Use **orders** when the user says orders, bookings, or volume of orders. Say which grain you used.

## Tables

### `sales.customers` (Sales.Customers)

| Column | Type | Notes |
|---|---|---|
| `customer_id` | int PK | |
| `customer_name` | text | |
| `customer_category_id` | int | → `customer_categories` |
| `buying_group_id` | int nullable | → `buying_groups` (e.g. tailspin-style groups in WWI) |
| `delivery_city_id` | int | → `application.cities` — **use this for region** |
| `account_opened_date` | date | |
| `credit_limit` | numeric nullable | |
| `is_on_credit_hold` | boolean | |
| `payment_days` | int | |
| `phone_number` | text | optional |
| `website_url` | text | optional |

Do not dump address blobs into answers unless asked.

### `sales.customer_categories` (Sales.CustomerCategories)

`customer_category_id`, `customer_category_name`

### `sales.buying_groups` (Sales.BuyingGroups)

`buying_group_id`, `buying_group_name`

### `sales.orders` (Sales.Orders)

| Column | Type | Notes |
|---|---|---|
| `order_id` | int PK | |
| `customer_id` | int | |
| `salesperson_person_id` | int | → `application.people` |
| `contact_person_id` | int | |
| `order_date` | date | **clock cutoff** |
| `expected_delivery_date` | date | |
| `picking_completed_when` | timestamp nullable | |
| `is_undersupply_backordered` | boolean | |

Header has no money. Money is on lines (unit price × quantity) or on invoices.

### `sales.order_lines` (Sales.OrderLines)

| Column | Type | Notes |
|---|---|---|
| `order_line_id` | int PK | |
| `order_id` | int | |
| `stock_item_id` | int | → `warehouse.stock_items` |
| `description` | text | |
| `quantity` | int | |
| `unit_price` | numeric nullable | |
| `tax_rate` | numeric | |
| `picked_quantity` | int | |

Booked value ≈ `quantity * unit_price` (ex-tax unless asked).

### `sales.invoices` (Sales.Invoices)

| Column | Type | Notes |
|---|---|---|
| `invoice_id` | int PK | |
| `customer_id` | int | |
| `order_id` | int nullable | |
| `invoice_date` | date | **clock cutoff** — primary “earned” date |
| `is_credit_note` | boolean | Subtract or exclude when totaling revenue |
| `total_dry_items` / chiller | int | optional |

### `sales.invoice_lines` (Sales.InvoiceLines)

| Column | Type | Notes |
|---|---|---|
| `invoice_line_id` | int PK | |
| `invoice_id` | int | |
| `stock_item_id` | int | |
| `description` | text | |
| `quantity` | int | |
| `unit_price` | numeric | |
| `tax_rate` | numeric | |
| `tax_amount` | numeric | |
| `line_profit` | numeric | WWI-supplied profit on the line — use when asked for profit, and **cite this column** |
| `extended_price` | numeric | Line extended price |

**Revenue** ≈ sum of `extended_price` on non-credit invoices (handle credit notes explicitly).

### `sales.customer_transactions` (Sales.CustomerTransactions)

Optional. `customer_transaction_id`, `customer_id`, `transaction_date` (**cutoff**), `amount_excluding_tax`, `tax_amount`, `transaction_amount`, `outstanding_balance`, `invoice_id`, `payment_method_id`, `finalization_date` (nullable; there is **no** `is_finalized` column). Use for cash collected vs invoiced if asked.

## Shared reads (not in `sales` schema)

Granted to `sales_agent_role`:

- `warehouse.stock_items` — names, brand, size, `unit_price` (list), `supplier_id`
- `application.cities`, `state_provinces`, `countries`
- `application.people` — salesperson / contact names

## Joins (typical)

```text
invoice_lines.invoice_id     → invoices.invoice_id
invoices.customer_id         → customers.customer_id
invoice_lines.stock_item_id  → warehouse.stock_items.stock_item_id
customers.delivery_city_id   → cities.city_id
cities.state_province_id     → state_provinces.state_province_id
state_provinces.country_id   → countries.country_id
orders.salesperson_person_id → people.person_id
order_lines.order_id         → orders.order_id
```

## Period helpers

Define periods from the demo clock in SQL (or Python) — do not hardcode `2016-01-01`.

- This month: `[date_trunc('month', clock), clock]`
- Last month: full calendar month before clock’s month
- This quarter: from quarter start of clock through clock
- Last quarter: the previous calendar quarter
- Last 3 months: `(clock - 3 months), clock`
- **Fiscal year:** calendar year. Q1 = Jan–Mar, Q2 = Apr–Jun, Q3 = Jul–Sep, Q4 = Oct–Dec. Label as `FYyyyy Qn` (e.g. clock `2015-09-14` → **FY2015 Q3**, 2015-07-01 through clock)
- This FY to date: `[date_trunc('year', clock), clock]`

## Do not

- Query `purchasing.*`
- Query `warehouse.stock_item_holdings` (Purchase / Insight)
- Return more than the row cap; aggregate in SQL for “performance” questions
- Ignore `is_credit_note`
