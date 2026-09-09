from __future__ import annotations

DISPLAY_SCHEMA = {
    "sales": "Sales",
    "purchasing": "Purchasing",
    "warehouse": "Warehouse",
    "application": "Application",
}

SALES_TABLES = frozenset(
    {
        "sales.customers",
        "sales.customer_categories",
        "sales.buying_groups",
        "sales.orders",
        "sales.order_lines",
        "sales.invoices",
        "sales.invoice_lines",
        "sales.customer_transactions",
        "warehouse.stock_items",
        "application.cities",
        "application.state_provinces",
        "application.countries",
        "application.people",
        "application.delivery_methods",
        "application.payment_methods",
    }
)

PURCHASE_TABLES = frozenset(
    {
        "purchasing.suppliers",
        "purchasing.supplier_categories",
        "purchasing.purchase_orders",
        "purchasing.purchase_order_lines",
        "purchasing.supplier_transactions",
        "warehouse.stock_items",
        "warehouse.stock_item_holdings",
        "warehouse.stock_item_transactions",
        "warehouse.stock_groups",
        "warehouse.stock_item_stock_groups",
        "warehouse.colors",
        "warehouse.package_types",
        "warehouse.on_hand_as_of",
        "application.cities",
        "application.state_provinces",
        "application.countries",
        "application.people",
        "application.delivery_methods",
        "application.payment_methods",
        "application.transaction_types",
    }
)

INSIGHT_TABLES = SALES_TABLES | PURCHASE_TABLES | frozenset({"copilot.alerts", "copilot.settings"})


def display_name(qualified: str) -> str:
    if "." not in qualified:
        return qualified
    schema, table = qualified.split(".", 1)
    pascal = "".join(part.capitalize() for part in table.replace("-", "_").split("_"))
    return f"{DISPLAY_SCHEMA.get(schema.lower(), schema.capitalize())}.{pascal}"


def display_names(tables: list[str]) -> list[str]:
    return [display_name(t) for t in tables]
