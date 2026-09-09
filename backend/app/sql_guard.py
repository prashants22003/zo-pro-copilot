from __future__ import annotations

import re

import sqlparse
from sqlparse.tokens import DML, Keyword

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|"
    r"do\s+\$|call|vacuum|lock|notify|listen|execute|prepare|deallocate|"
    r"set\s+|reset\s+|into\s+outfile|pg_sleep|lo_import|dblink)\b",
    re.I,
)
_QUALIFIED = re.compile(
    r"\b(sales|purchasing|warehouse|application|copilot)\.([a-z_][a-z0-9_]*)",
    re.I,
)


class SqlGuardError(ValueError):
    pass


def _first_dml(sql: str) -> str | None:
    parsed = sqlparse.parse(sql)
    if not parsed:
        raise SqlGuardError("Could not parse SQL.")
    if len(parsed) > 1:
        raise SqlGuardError("Only a single statement is allowed.")
    stmt = parsed[0]
    for token in stmt.flatten():
        if token.ttype is DML:
            return token.value.upper()
        if token.ttype is Keyword and token.value.upper() in {"WITH", "SELECT"}:
            if token.value.upper() == "SELECT":
                return "SELECT"
            continue
    return None


def validate_select(sql: str, allow: frozenset[str]) -> str:
    stripped = sql.strip().rstrip(";")
    if not stripped:
        raise SqlGuardError("Empty SQL.")
    if ";" in stripped:
        raise SqlGuardError("Multiple statements are not allowed.")
    if _FORBIDDEN.search(stripped):
        raise SqlGuardError("That statement type is not allowed.")
    dml = _first_dml(stripped)
    if dml not in {None, "SELECT"}:
        raise SqlGuardError("Only SELECT queries are allowed.")
    if "select" not in stripped.lower():
        raise SqlGuardError("Only SELECT queries are allowed.")
    found = {f"{s.lower()}.{t.lower()}" for s, t in _QUALIFIED.findall(stripped)}
    if not found:
        raise SqlGuardError("Qualify every table as schema.table (e.g. sales.orders).")
    extra = found - set(allow)
    if extra:
        raise SqlGuardError(f"Tables not on this agent's allow-list: {', '.join(sorted(extra))}")
    return stripped


def referenced_tables(sql: str) -> list[str]:
    return sorted({f"{s.lower()}.{t.lower()}" for s, t in _QUALIFIED.findall(sql)})


def cap_sql(sql: str, limit: int) -> str:
    low = sql.lower()
    if re.search(r"\blimit\s+\d+\s*$", low):
        return sql
    return f"SELECT * FROM (\n{sql}\n) AS _zopro_capped LIMIT {int(limit)}"
