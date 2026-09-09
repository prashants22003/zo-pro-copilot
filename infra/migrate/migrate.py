"""One-time WWI .bak → Postgres allow-list copy. CPU/RAM only; no GPU."""

from __future__ import annotations

import os
import re
import sys
import time
from decimal import Decimal
from uuid import UUID

import pymssql
import psycopg
from tables import INDEXES, SKIP_COLUMN_NAMES, SKIP_TYPE_NAMES, TABLES

MSSQL_HOST = os.environ.get("MSSQL_HOST", "sqlserver")
MSSQL_SA_PASSWORD = os.environ["MSSQL_SA_PASSWORD"]
BAK_PATH = os.environ.get("BAK_PATH", "/var/opt/mssql/backup/wwi.bak")
PG_DSN = os.environ["PG_DSN"]
BATCH = int(os.environ.get("COPY_BATCH", "4000"))
REPORT_PATH = os.environ.get("REPORT_PATH", "/dump/migrate-report.txt")


def log(msg: str) -> None:
    print(msg, flush=True)


def snake(name: str) -> str:
    name = name.replace("ID", "Id")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def wait_mssql(timeout: int = 180) -> pymssql.Connection:
    log(f"Waiting for SQL Server at {MSSQL_HOST}:1433 …")
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            conn = pymssql.connect(
                server=MSSQL_HOST,
                user="sa",
                password=MSSQL_SA_PASSWORD,
                database="master",
                login_timeout=15,
                timeout=0,
                autocommit=True,
            )
            conn.cursor().execute("SELECT 1")
            log("SQL Server is up.")
            return conn
        except Exception as exc:
            last = exc
            time.sleep(5)
    raise SystemExit(f"SQL Server did not become ready: {last}")


def wait_postgres(timeout: int = 120) -> psycopg.Connection:
    log("Waiting for Postgres …")
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            conn = psycopg.connect(PG_DSN, autocommit=True)
            conn.execute("SELECT 1")
            log("Postgres is up.")
            return conn
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise SystemExit(f"Postgres did not become ready: {last}")


def restore_bak(conn: pymssql.Connection) -> None:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sys.databases WHERE name = 'WideWorldImporters'")
    if cur.fetchone():
        log("WideWorldImporters already restored — skipping RESTORE.")
        return

    log(f"RESTORE FILELISTONLY from {BAK_PATH}")
    cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{BAK_PATH}'")
    files = cur.fetchall()
    # LogicalName, PhysicalName, Type, FileGroupName, Size, … FileId is index 6
    moves = []
    for row in files:
        logical = row[0]
        ftype = row[2]
        if isinstance(ftype, bytes):
            ftype = ftype.decode("ascii")
        file_id = row[6]
        if ftype == "L":
            dest = f"/var/opt/mssql/data/{logical}.ldf"
        elif ftype == "S":
            dest = f"/var/opt/mssql/data/{logical}"
        else:
            ext = ".mdf" if file_id == 1 else ".ndf"
            dest = f"/var/opt/mssql/data/{logical}{ext}"
        moves.append(f"MOVE N'{logical}' TO N'{dest}'")
        log(f"  {logical} ({ftype}) -> {dest}")

    sql = (
        f"RESTORE DATABASE [WideWorldImporters] FROM DISK = N'{BAK_PATH}' WITH "
        + ", ".join(moves)
        + ", REPLACE, STATS = 10"
    )
    log("Restoring database (this can take several minutes; CPU/disk only) …")
    cur.execute(sql)
    while True:
        cur.execute(
            "SELECT state_desc FROM sys.databases WHERE name = 'WideWorldImporters'"
        )
        row = cur.fetchone()
        if row and str(row[0]) == "ONLINE":
            break
        time.sleep(3)
    log("RESTORE complete, database ONLINE.")


def map_type(type_name: str, precision: int, scale: int, max_length: int) -> str:
    t = type_name.lower()
    if t in ("int", "tinyint", "smallint"):
        return "integer"
    if t == "bigint":
        return "bigint"
    if t == "bit":
        return "boolean"
    if t in ("decimal", "numeric", "money", "smallmoney"):
        p = precision or 18
        s = scale or 0
        return f"numeric({p},{s})"
    if t in ("float", "real"):
        return "double precision"
    if t == "date":
        return "date"
    if t == "time":
        return "time"
    if t in ("datetime", "datetime2", "smalldatetime"):
        return "timestamp"
    if t == "datetimeoffset":
        return "timestamptz"
    if t == "uniqueidentifier":
        return "uuid"
    if t in ("nvarchar", "varchar", "nchar", "char", "text", "ntext"):
        return "text"
    if t == "sysname":
        return "text"
    return "text"


def mssql_columns(conn: pymssql.Connection, schema: str, table: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.name, ty.name, c.max_length, c.precision, c.scale, c.is_nullable, c.is_computed
        FROM sys.columns c
        JOIN sys.types ty ON c.user_type_id = ty.user_type_id
        WHERE c.object_id = OBJECT_ID(%s)
        ORDER BY c.column_id
        """,
        (f"[{schema}].[{table}]",),
    )
    cols = []
    for name, type_name, max_length, precision, scale, is_nullable, is_computed in cur:
        if is_computed:
            continue
        if name in SKIP_COLUMN_NAMES:
            continue
        if type_name.lower() in SKIP_TYPE_NAMES:
            continue
        cols.append(
            {
                "src": name,
                "dst": snake(name),
                "pg": map_type(type_name, precision, scale, max_length),
                "nullable": bool(is_nullable),
                "type_name": type_name.lower(),
            }
        )
    if not cols:
        raise RuntimeError(f"No copyable columns on {schema}.{table}")
    return cols


def pk_columns(conn: pymssql.Connection, schema: str, table: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.COLUMN_NAME
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE c
          ON tc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
         AND tc.TABLE_SCHEMA = c.TABLE_SCHEMA
        WHERE tc.TABLE_SCHEMA = %s AND tc.TABLE_NAME = %s
          AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        ORDER BY c.ORDINAL_POSITION
        """,
        (schema, table),
    )
    return [snake(r[0]) for r in cur.fetchall()]


def convert_cell(value, type_name: str):
    if value is None:
        return None
    if type_name == "bit":
        return bool(value)
    if type_name == "uniqueidentifier":
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
    if type_name in ("money", "smallmoney", "decimal", "numeric") and not isinstance(
        value, Decimal
    ):
        return Decimal(str(value))
    return value


def copy_table(
    mssql: pymssql.Connection,
    pg: psycopg.Connection,
    src_schema: str,
    src_table: str,
    dst_schema: str,
    dst_table: str,
) -> int:
    cols = mssql_columns(mssql, src_schema, src_table)
    ident = f"{dst_schema}.{dst_table}"
    exists = pg.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (dst_schema, dst_table),
    ).fetchone()[0]
    if exists:
        n = pg.execute(f"SELECT COUNT(*) FROM {ident}").fetchone()[0]
        if n > 0:
            log(f"  skip {ident} (already {n} rows)")
            return n
        pg.execute(f"DROP TABLE {ident} CASCADE")

    col_defs = []
    for c in cols:
        col_defs.append(f'{c["dst"]} {c["pg"]}')
    pg.execute(f"CREATE TABLE {ident} ({', '.join(col_defs)})")

    select_list = ", ".join(f'[{c["src"]}]' for c in cols)
    src_sql = f"SELECT {select_list} FROM [{src_schema}].[{src_table}]"
    mcur = mssql.cursor()
    mcur.execute(src_sql)

    names = [c["dst"] for c in cols]
    copy_sql = f"COPY {ident} ({', '.join(names)}) FROM STDIN"
    copied = 0
    log(f"  copying {src_schema}.{src_table} → {ident}")
    with pg.cursor() as pcur:
        with pcur.copy(copy_sql) as copy:
            while True:
                rows = mcur.fetchmany(BATCH)
                if not rows:
                    break
                for row in rows:
                    out = tuple(
                        convert_cell(v, cols[i]["type_name"]) for i, v in enumerate(row)
                    )
                    copy.write_row(out)
                copied += len(rows)
                if copied % (BATCH * 5) == 0:
                    log(f"    {ident}: {copied} rows …")
    pks = pk_columns(mssql, src_schema, src_table)
    pk_ok = [c for c in pks if c in names]
    if pk_ok:
        pg.execute(
            f"ALTER TABLE {ident} ADD PRIMARY KEY ({', '.join(pk_ok)})"
        )
    log(f"  {ident}: {copied} rows")
    return copied


def seed_copilot(pg: psycopg.Connection) -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "roles.sql")
    pg.execute(open(sql_path, encoding="utf-8").read())
    log("copilot schema + roles applied.")


def verify(pg: psycopg.Connection, counts: dict[str, int]) -> str:
    lines = ["Zo-Pro Copilot — migrate report", ""]
    for key, n in counts.items():
        lines.append(f"  {key}: {n}")
    q = pg.execute("SELECT MIN(order_date), MAX(order_date), COUNT(*) FROM sales.orders")
    omin, omax, oc = q.fetchone()
    lines.append(f"  sales.orders date range: {omin} → {omax} ({oc} rows)")
    q = pg.execute(
        "SELECT MIN(invoice_date), MAX(invoice_date) FROM sales.invoices"
    )
    imin, imax = q.fetchone()
    lines.append(f"  sales.invoices date range: {imin} → {imax}")
    q = pg.execute(
        """
        SELECT SIGN(quantity) AS s, COUNT(*) 
        FROM warehouse.stock_item_transactions
        GROUP BY 1 ORDER BY 1
        """
    )
    lines.append("  stock_item_transactions quantity signs:")
    for s, n in q:
        lines.append(f"    sign={s}: {n}")
    q = pg.execute(
        """
        SELECT SUM(quantity) FROM warehouse.stock_item_transactions
        """
    )
    lines.append(f"  sum(quantity) all transactions: {q.fetchone()[0]}")
    q = pg.execute(
        "SELECT SUM(quantity_on_hand) FROM warehouse.stock_item_holdings"
    )
    lines.append(f"  sum(quantity_on_hand) holdings snapshot: {q.fetchone()[0]}")
    text = "\n".join(lines) + "\n"
    log(text)
    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        log(f"Wrote {REPORT_PATH}")
    except OSError as exc:
        log(f"Could not write report file: {exc}")
    return text


def already_seeded(pg: psycopg.Connection) -> bool:
    row = pg.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'sales' AND table_name = 'orders'
        )
        """
    ).fetchone()[0]
    if not row:
        return False
    n = pg.execute("SELECT COUNT(*) FROM sales.orders").fetchone()[0]
    return n > 0


def main() -> int:
    log("Phase 1 migrate: SQL Server .bak → Postgres allow-list")
    log("This workload is CPU / RAM / disk. It does not use the GPU.")
    mssql_master = wait_mssql()
    restore_bak(mssql_master)
    mssql_master.close()

    mssql = pymssql.connect(
        server=MSSQL_HOST,
        user="sa",
        password=MSSQL_SA_PASSWORD,
        database="WideWorldImporters",
        login_timeout=30,
        timeout=0,
        autocommit=True,
    )
    pg = wait_postgres()
    if already_seeded(pg):
        log("Postgres already has sales.orders rows — skipping copy.")
        seed_copilot(pg)
        verify(pg, {"sales.orders": pg.execute("SELECT COUNT(*) FROM sales.orders").fetchone()[0]})
        return 0

    pg.execute("CREATE SCHEMA IF NOT EXISTS sales")
    pg.execute("CREATE SCHEMA IF NOT EXISTS purchasing")
    pg.execute("CREATE SCHEMA IF NOT EXISTS warehouse")
    pg.execute("CREATE SCHEMA IF NOT EXISTS application")
    pg.execute("CREATE SCHEMA IF NOT EXISTS copilot")

    counts = {}
    for src_schema, src_table, dst_schema, dst_table in TABLES:
        n = copy_table(mssql, pg, src_schema, src_table, dst_schema, dst_table)
        counts[f"{dst_schema}.{dst_table}"] = n

    log("Creating indexes …")
    for stmt in INDEXES:
        pg.execute(stmt)

    seed_copilot(pg)
    verify(pg, counts)
    log("Migrate finished. Next: pg_dump from the host script.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
