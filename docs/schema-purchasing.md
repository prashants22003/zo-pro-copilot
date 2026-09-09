# Schema — Purchasing allow-list

Physical names first. Display names for the UI in parentheses.

Clock cutoff: parent `purchase_orders.order_date` ≤ clock. Receipts: `last_receipt_date` and `supplier_transactions.transaction_date`.

## Look here first

| Question about… | Start here |
|---|---|
| POs placed, spend committed | `purchasing.purchase_orders` + `purchase_order_lines` |
| Who we buy from | `purchasing.suppliers` |
| Overdue / not received | lines where `is_order_line_finalized` is false and `expected_delivery_date` < clock |
| Unit cost | `expected_unit_price_per_outer` / `warehouse.stock_items.quantity_per_outer` |
| Lead time | `warehouse.stock_items.lead_time_days`; also `expected_delivery_date - order_date` |
| Stock vs inbound | `warehouse.stock_item_transactions` (on-hand as of clock) + open PO lines |
| Supplier region | `suppliers.delivery_city_id` → `application.cities` → states → countries |

## Tables

### `purchasing.suppliers` (Purchasing.Suppliers)

| Column | Type | Notes |
|---|---|---|
| `supplier_id` | int PK | |
| `supplier_name` | text | |
| `supplier_category_id` | int | |
| `primary_contact_person_id` | int | → `application.people` |
| `delivery_city_id` | int | region |
| `payment_days` | int | |
| `phone_number` | text | optional |
| `delivery_method_id` | int nullable | |

### `purchasing.supplier_categories` (Purchasing.SupplierCategories)

`supplier_category_id`, `supplier_category_name`

### `purchasing.purchase_orders` (Purchasing.PurchaseOrders)

| Column | Type | Notes |
|---|---|---|
| `purchase_order_id` | int PK | |
| `supplier_id` | int | |
| `order_date` | date | **clock cutoff** |
| `expected_delivery_date` | date | overdue if `< clock` and not finalized |
| `delivery_method_id` | int | |
| `contact_person_id` | int | |
| `is_order_finalized` | boolean | |

### `purchasing.purchase_order_lines` (Purchasing.PurchaseOrderLines)

| Column | Type | Notes |
|---|---|---|
| `purchase_order_line_id` | int PK | |
| `purchase_order_id` | int | |
| `stock_item_id` | int | → `warehouse.stock_items` |
| `ordered_outers` | int | pack count, not eaches |
| `description` | text | |
| `received_outers` | int | |
| `expected_unit_price_per_outer` | numeric | |
| `is_order_line_finalized` | boolean | |
| `last_receipt_date` | date nullable | |
| `package_type_id` | int | |

**Each quantity** ≈ `ordered_outers * stock_items.quantity_per_outer`.

**Line spend** ≈ `ordered_outers * expected_unit_price_per_outer`.

Open / overdue: not finalized AND parent `expected_delivery_date < clock`.

### `purchasing.supplier_transactions` (Purchasing.SupplierTransactions)

`supplier_transaction_id`, `supplier_id`, `transaction_type_id`, `transaction_date` (**cutoff**), `amount_excluding_tax`, `tax_amount`, `transaction_amount`, `outstanding_balance`, `purchase_order_id`, `finalization_date` (nullable; there is **no** `is_finalized` column). Use for actual spend vs PO expected cost.

## Shared reads

- `warehouse.stock_items`, `stock_item_holdings` (bin, reorder **targets** — not as-of qty), `stock_item_transactions`
- `application.cities`, `state_provinces`, `countries`, `people`

On-hand as of clock: holdings is end-state (2016-05-31). Use

`quantity_on_hand - SUM(transactions.quantity WHERE transaction_occurred_when::date > clock)`.

Do not `SUM` all transactions as if the warehouse started at zero (it does not).

## Joins

```text
purchase_order_lines.purchase_order_id → purchase_orders.purchase_order_id
purchase_orders.supplier_id            → suppliers.supplier_id
purchase_order_lines.stock_item_id     → warehouse.stock_items.stock_item_id
stock_items.supplier_id                → suppliers.supplier_id
suppliers.delivery_city_id             → cities.city_id
```

## Do not

- Query `sales.*`
- Treat `ordered_outers` as eaches
- Use holdings quantity as historical on-hand
