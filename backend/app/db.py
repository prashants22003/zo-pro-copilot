from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, memoryview):
        return bytes(value).hex()
    return value


def jsonable_row(row: dict) -> dict:
    return {k: _jsonable(v) for k, v in row.items()}


@contextmanager
def connection(url: str, timeout_ms: int | None = None):
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True, connect_timeout=5)
    try:
        if timeout_ms:
            conn.execute(f"SET statement_timeout = {int(timeout_ms)}")
        yield conn
    finally:
        conn.close()


def owner_conn():
    s = get_settings()
    return connection(s.database_url, s.query_timeout_ms)


def sales_conn():
    s = get_settings()
    return connection(s.sales_database_url, s.query_timeout_ms)


def purchase_conn():
    s = get_settings()
    return connection(s.purchase_database_url, s.query_timeout_ms)


def insight_conn(timeout_ms: int | None = None):
    s = get_settings()
    return connection(s.insight_database_url, timeout_ms or 15000)


def get_clock() -> date:
    with owner_conn() as conn:
        row = conn.execute(
            "SELECT value FROM copilot.settings WHERE key = 'demo_clock'"
        ).fetchone()
    if not row:
        return date(2015, 9, 14)
    return date.fromisoformat(row["value"])


def set_clock(value: date) -> date:
    with owner_conn() as conn:
        conn.execute(
            """
            INSERT INTO copilot.settings (key, value) VALUES ('demo_clock', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (value.isoformat(),),
        )
    return value


def order_date_bounds() -> tuple[date, date]:
    with owner_conn() as conn:
        row = conn.execute(
            "SELECT MIN(order_date) AS lo, MAX(order_date) AS hi FROM sales.orders"
        ).fetchone()
    return row["lo"], row["hi"]


def is_seeded() -> bool:
    try:
        with owner_conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM sales.orders").fetchone()
        return bool(row and row["n"] > 0)
    except Exception:
        return False
