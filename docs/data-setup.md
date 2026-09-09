# Data setup — Wide World Importers → Postgres

## 1. Source file

| | |
|---|---|
| Path | `data/WideWorldImporters-Full.bak` |
| Kind | SQL Server **OLTP Full** backup (not `WideWorldImportersDW`) |
| Size | ~121 MB on disk |
| Everyday seed | `data/wwi-postgres.dump` (`pg_dump -Fc`) after phase 1 |
| App database | **PostgreSQL**. The API never talks to SQL Server. |

The CSVs under `data/unused/` are **not** used. Do not seed them.

Do not commit the `.bak` or the dump (large binaries).

Phase 1 does **not** use the GPU. SQL Server in Docker is capped at 2 GB RAM (`infra/migrate/run.ps1`).

## 2. Phase 1 (once): `.bak` → dump

A `.bak` cannot be restored by Postgres. One-time job in `infra/migrate`:

1. Restore the backup into SQL Server (Docker, RAM-capped).
2. Copy the **allow-listed** tables into Postgres with types mapped.
3. Create schemas `sales`, `purchasing`, `warehouse`, `application`, `copilot`.
4. Create roles and GRANTs.
5. `pg_dump -Fc` → `data/wwi-postgres.dump`, write `data/migrate-report.txt`.
6. Stop SQL Server.

MVP Compose only restores the dump when Postgres is empty. Re-run phase 1 only if the allow-list or type mapping changes.

## 3. Empty detection

Treat Postgres as **seeded** when all are true:

- Schema `sales` exists
- Table `sales.orders` exists
- `SELECT COUNT(*) FROM sales.orders` > 0

Otherwise run a full migrate. Do not half-seed.

## 4. Identifier convention

WWI on SQL Server uses schemas `Sales`, `Purchasing`, `Warehouse`, `Application` and PascalCase tables.

In Postgres:

- Schemas: `sales`, `purchasing`, `warehouse`, `application`, `copilot`
- Tables/columns: `snake_case` (`order_lines`, `stock_item_id`)
- UI display names: `Sales.Orders` (see each schema doc)

Agents generate SQL against **physical** names. Citations in the UI use **display** names.

## 5. Type mapping

| SQL Server | Postgres |
|---|---|
| `int` / `bigint` | `integer` / `bigint` |
| `decimal` / `money` | `numeric` |
| `nvarchar` / `varchar` | `text` |
| `datetime2` / `datetime` | `timestamp` (no time zone; WWI is naive) |
| `date` | `date` |
| `bit` | `boolean` |
| `uniqueidentifier` | `uuid` |
| `varbinary` / `image` | skip (photos) |
| `geography` / `hierarchyid` / `xml` | skip or `text` if needed |

Drop temporal history tables (`ValidFrom`/`ValidTo` system versioning). Keep current-row attributes that matter (`account_opened_date`, etc.).

## 6. Allow-listed objects to copy

Full lists and columns: schema docs. Do not copy `Website.*`, `Sequences.*`, cold-room/vehicle telemetry, or application-wide audit dumps.

**sales:** `customers`, `customer_categories`, `buying_groups`, `orders`, `order_lines`, `invoices`, `invoice_lines`, `customer_transactions` (optional but useful for money received)

**purchasing:** `suppliers`, `supplier_categories`, `purchase_orders`, `purchase_order_lines`, `supplier_transactions`

**warehouse:** `stock_items`, `stock_item_holdings`, `stock_item_transactions`, `stock_groups`, `stock_item_stock_groups`, `package_types`, `colors`

**application:** `people`, `cities`, `state_provinces`, `countries`, `delivery_methods`, `payment_methods`, `transaction_types`

**copilot (created, not from bak):** `alerts`, `settings` (includes `demo_clock`)

Preserve primary keys and foreign keys that the allow-list needs (`orders.customer_id` → `customers`, `order_lines.stock_item_id` → `stock_items`, `customers.delivery_city_id` → `cities`, …).

## 7. Roles

```text
app_owner            — migrate, DDL, copilot writes from insight job
sales_agent_role     — SELECT on sales allow-list + warehouse.stock_items
                       + application.cities, state_provinces, countries, people
purchase_agent_role  — SELECT on purchasing allow-list + warehouse.* allow-list
                       + application.cities, state_provinces, countries, people
insight_role         — SELECT on union of both; INSERT/UPDATE on copilot.alerts
                       SELECT/UPDATE on copilot.settings
```

No INSERT/UPDATE/DELETE on WWI tables for any agent role. Statement timeout at the role or session level.

## 8. Demo clock

WWI OLTP data is roughly **2013 through mid-2016**. Wall-clock “this week” in 2026 would return nothing.

| Rule | |
|---|---|
| Setting | `copilot.settings.demo_clock` (`date`), default from `DEMO_CLOCK` env, e.g. `2015-09-14` |
| UI | Header control; `PATCH /clock` persists for the process (MVP: single shared clock is fine) |
| Cutoff | Ignore transactional rows with date **>** clock (clock day is included) |
| Relative phrases | “Today” = clock. “Last month” = calendar month before the clock’s month. “This quarter” / “this FY quarter” = calendar quarter of the clock through the clock. “Last quarter” = the previous calendar quarter. **Fiscal year = calendar year** (Q1 Jan–Mar). On `2015-09-14` that is FY2015 Q3 |

Dated columns (apply cutoff here):

| Table | Date column |
|---|---|
| `sales.orders` | `order_date` |
| `sales.invoices` | `invoice_date` |
| `sales.customer_transactions` | `transaction_date` |
| `purchasing.purchase_orders` | `order_date` |
| `purchasing.purchase_order_lines` | `last_receipt_date` (nullable; still filter parent PO) |
| `purchasing.supplier_transactions` | `transaction_date` |
| `warehouse.stock_item_transactions` | `transaction_occurred_when` |

**Stock on hand as of clock:** `warehouse.stock_item_holdings` is the snapshot at **data-end** (2016-05-31), not a historical series. Transaction quantities do **not** sum to holdings (opening stock is not in the transaction table). Reconstruct:

```sql
-- on_hand(clock) = holdings_at_end - movements_after_clock
SELECT h.stock_item_id,
       h.quantity_on_hand - COALESCE(SUM(t.quantity) FILTER (
           WHERE t.transaction_occurred_when::date > :clock
       ), 0) AS qty_on_hand
FROM warehouse.stock_item_holdings h
LEFT JOIN warehouse.stock_item_transactions t ON t.stock_item_id = h.stock_item_id
GROUP BY h.stock_item_id, h.quantity_on_hand;
```

When `clock` equals data-end, the filter is empty and on-hand = holdings. Sales issues in WWI are **negative** `quantity`; receipts are positive. Verified on seed: mixed signs, holdings ≠ `SUM(all transactions)`.

Dimensions (customers, stock items, cities) are **not** date-cut unless a valid-from/to exists; use current dimension rows.

Suggested demo starting clock: **2015-09-14**. Seeded range: `sales.orders.order_date` **2013-01-01 → 2016-05-31**.

## 9. Re-seed (MVP)

```text
docker compose down -v
docker compose up --build
```

Empty Postgres restores `data/wwi-postgres.dump` (fast). To rebuild that dump from the `.bak`, run `powershell -File infra/migrate/run.ps1`.
