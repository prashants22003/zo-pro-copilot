# Schema — Warehouse allow-list

Display prefix: `Warehouse.*`.

Sales agent: **`stock_items` only**.  
Purchase + Insight: `stock_items`, `stock_item_holdings`, `stock_item_transactions`, groups/colors/packages as needed.

## Look here first

| Question about… | Start here |
|---|---|
| Product name, brand, list price, supplier of the SKU | `warehouse.stock_items` |
| Reorder level / target (policy) | `warehouse.stock_item_holdings` |
| Quantity on hand **as of clock** | `warehouse.stock_item_transactions` (sum `quantity`) |
| Stock groups | `stock_groups` + `stock_item_stock_groups` |

## `warehouse.stock_items` (Warehouse.StockItems)

| Column | Type | Notes |
|---|---|---|
| `stock_item_id` | int PK | Join key for sales and purchasing lines |
| `stock_item_name` | text | |
| `supplier_id` | int | Usual supplier |
| `brand` | text nullable | |
| `size` | text nullable | |
| `lead_time_days` | int | |
| `quantity_per_outer` | int | Converts PO outers → units |
| `is_chiller_stock` | boolean | |
| `tax_rate` | numeric | |
| `unit_price` | numeric | Selling list price (not a fact table) |
| `recommended_retail_price` | numeric nullable | |
| `typical_weight_per_unit` | numeric | |
| `color_id` | int nullable | → `colors` |
| `unit_package_id` / `outer_package_id` | int | → `package_types` |

Skip `photo`, `custom_fields`, search blobs.

## `warehouse.stock_item_holdings` (Warehouse.StockItemHoldings)

PK `stock_item_id` (1:1 with stock items).

| Column | Notes |
|---|---|
| `quantity_on_hand` | Snapshot at **backup data-end**, not historical. Do not use when clock ≠ data-end |
| `bin_location` | |
| `last_stocktake_quantity` | |
| `last_cost_price` | |
| `reorder_level` | Policy |
| `target_stock_level` | Policy |

## `warehouse.stock_item_transactions` (Warehouse.StockItemTransactions)

| Column | Notes |
|---|---|
| `stock_item_transaction_id` | PK |
| `stock_item_id` | |
| `transaction_type_id` | → `application.transaction_types` |
| `customer_id` / `invoice_id` / `supplier_id` / `purchase_order_id` | nullable, as applicable |
| `quantity` | **Signed.** Issues negative, receipts positive (locked on this backup) |
| `transaction_occurred_when` | timestamp; cutoff on `::date` |

On-hand as of clock:

```sql
SELECT h.stock_item_id,
       h.quantity_on_hand
       - COALESCE(SUM(t.quantity) FILTER (
             WHERE t.transaction_occurred_when::date > :clock
         ), 0) AS qty_on_hand
FROM warehouse.stock_item_holdings h
LEFT JOIN warehouse.stock_item_transactions t ON t.stock_item_id = h.stock_item_id
GROUP BY h.stock_item_id, h.quantity_on_hand;
```

Verified on this backup: `quantity` is signed (issues negative, receipts positive). `SUM(all transactions)` does **not** equal holdings — there is opening stock outside the transaction table. Back out movements **after** the clock from the end snapshot.

## Other

- `warehouse.colors` — `color_id`, `color_name`
- `warehouse.package_types` — `package_type_id`, `package_type_name`
- `warehouse.stock_groups` / `stock_item_stock_groups` — product grouping

## Do not

- Let the Sales agent read transactions or holdings
- Use raw `quantity_on_hand` when the clock is before 2016-05-31 — always apply the reconstruction SQL above
