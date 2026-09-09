from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

_ID = re.compile(r"(^id$|_id$|_key$|_uuid$)", re.I)
_NAME = re.compile(r"(name|title|label|region|customer|supplier|item|product)", re.I)
_DATE = re.compile(
    r"(date|month|period|week|year|quarter|as_of|clock)",
    re.I,
)
_SHARE = re.compile(r"(share|pct|percent|mix|portion|ratio)", re.I)
_MONEY = re.compile(
    r"(profit|revenue|price|amount|spend|value|extended|sales|cost|total)",
    re.I,
)
_DATE_VAL = re.compile(r"^\d{4}-\d{2}(-\d{2})?(T|\s|$)")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


_FRIENDLY = {
    "t30": "last 30 days",
    "p30": "prior 30 days",
}


def _labelize(key: str) -> str:
    k = (key or "").strip()
    if k.lower() in _FRIENDLY:
        return _FRIENDLY[k.lower()]
    return k.replace("_", " ").strip() or key


def _fmt(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        n = float(round(n))
        if abs(n) >= 1000:
            return f"{n:,.0f}"
        return f"{n:.0f}"
    if abs(n) >= 1000:
        return f"{n:,.2f}"
    return f"{n:.2f}"


def _dateish(key: str, sample: Any) -> bool:
    if _DATE.search(key or ""):
        return True
    if isinstance(sample, (date, datetime)):
        return True
    if isinstance(sample, str) and _DATE_VAL.match(sample.strip()):
        return True
    return False


def _cols(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _numeric_keys(rows: list[dict], keys: list[str]) -> list[str]:
    out = []
    for k in keys:
        if _ID.search(k):
            continue
        vals = [r.get(k) for r in rows]
        if any(_is_num(v) for v in vals):
            out.append(k)
    return out


def _label_key(rows: list[dict], keys: list[str], numeric: list[str]) -> str | None:
    text_keys = []
    for k in keys:
        if k in numeric or _ID.search(k):
            continue
        sample = next((r.get(k) for r in rows if r.get(k) is not None), None)
        if sample is not None:
            text_keys.append(k)
    for k in text_keys:
        if _NAME.search(k):
            return k
    if text_keys:
        return text_keys[0]
    for k in keys:
        if k not in numeric:
            return k
    return keys[0] if keys else None


def _pick_metric(numeric: list[str]) -> str | None:
    if not numeric:
        return None
    for pred in (_MONEY, _SHARE):
        for k in numeric:
            if pred.search(k):
                return k
    return numeric[0]


def _series(rows: list[dict], key: str) -> list[float]:
    out = []
    for r in rows:
        v = r.get(key)
        out.append(float(v) if _is_num(v) else 0.0)
    return out


def _labels(rows: list[dict], key: str | None) -> list[str]:
    if not key:
        return [str(i + 1) for i in range(len(rows))]
    labels = []
    for r in rows:
        v = r.get(key)
        if v is None:
            labels.append("—")
        else:
            s = str(v)
            labels.append(s[:24] + ("…" if len(s) > 24 else ""))
    return labels


def _flagged(values: list[float], rows: list[dict], subject_key: str | None) -> list[int]:
    if subject_key:
        needle = str(subject_key)
        tail = needle.split(":")[-1]
        hits = [
            i
            for i, r in enumerate(rows)
            if any(str(v) in {needle, tail} for v in r.values() if v is not None)
        ]
        if hits:
            return hits[:3]
    if not values:
        return []
    best = max(range(len(values)), key=lambda i: abs(values[i]))
    return [best]


def present(rows: list[dict], subject_key: str | None = None) -> dict:
    """Infer KPIs + a live chart spec from query rows. No LLM."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return {"kpis": [], "chart": None, "flagged_row_indexes": []}

    keys = _cols(rows)
    numeric = _numeric_keys(rows, keys)

    if len(rows) == 1:
        kpis = [
            {"value": _fmt(float(rows[0][k])), "label": _labelize(k)}
            for k in numeric
            if _is_num(rows[0].get(k))
        ]
        return {"kpis": kpis[:6], "chart": None, "flagged_row_indexes": [0] if rows else []}

    label_k = _label_key(rows, keys, numeric)
    metric_k = _pick_metric(numeric)
    if not metric_k:
        return {"kpis": [], "chart": None, "flagged_row_indexes": []}

    capped = rows[:16]
    values = _series(capped, metric_k)
    labels = _labels(capped, label_k)
    sample = next((r.get(label_k) for r in capped if r.get(label_k) is not None), None)
    positive = all(v >= 0 for v in values) and sum(values) > 0
    shareish = bool(_SHARE.search(metric_k or ""))
    dateish = _dateish(label_k or "", sample)

    extra_series = []
    extras = [k for k in numeric if k != metric_k][:2]
    if extras and (dateish or not shareish):
        for k in extras:
            extra_series.append({"name": _labelize(k), "values": _series(capped, k)})

    if dateish:
        kind = "line"
    elif positive and shareish and 2 <= len(capped) <= 8:
        kind = "pie"
        if len(capped) > 7:
            head_v, head_l = values[:6], labels[:6]
            other = sum(values[6:])
            values = head_v + [other]
            labels = head_l + ["Other"]
            capped = capped[:6]
    elif max((len(x) for x in labels), default=0) > 16 or len(capped) > 10:
        kind = "hbar"
        values, labels, capped = values[:12], labels[:12], capped[:12]
    else:
        kind = "bar"
        values, labels, capped = values[:12], labels[:12], capped[:12]

    flagged = _flagged(values, capped, subject_key)
    highlight = flagged[0] if flagged else 0
    if extra_series:
        extra_series = [{**s, "values": s["values"][: len(values)]} for s in extra_series]
    chart: dict[str, Any] = {
        "type": kind,
        "labels": labels,
        "values": values,
        "value_label": _labelize(metric_k),
        "highlight_index": highlight,
    }
    if extra_series and kind in {"line", "bar", "hbar"}:
        chart["series"] = extra_series

    kpis = []
    if values:
        kpis.append({"value": _fmt(sum(values) if kind == "pie" else values[highlight]), "label": _labelize(metric_k)})
        if extra_series and kind != "pie":
            s0 = extra_series[0]
            if highlight < len(s0["values"]):
                kpis.append({"value": _fmt(s0["values"][highlight]), "label": s0["name"]})
        kpis.append({"value": str(len(rows)), "label": "rows"})

    return {
        "kpis": kpis[:4],
        "chart": chart,
        "flagged_row_indexes": flagged,
    }
