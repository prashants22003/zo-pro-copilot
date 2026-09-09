from __future__ import annotations

import re
from datetime import date

from .clock import windows

_PERF = re.compile(
    r"\b("
    r"how did|how do|how was|how were|how have|how has|how we|"
    r"perform(?:ance|ed|ing)?|revenue|sales|sold|earn(?:ed|ings)?|"
    r"invoic\w*|orders?\b|supplier|stock|compared?|growth|grew|grow|"
    r"spend|margin|overdue|customers?|product|profit|booked|vs\b|"
    r"top\b|best\b|worst\b|rank"
    r")\b",
    re.I,
)

_CLOCK = re.compile(
    r"\b("
    r"today|tonight|date|clock|as[- ]of|"
    r"quarter|q[1-4]|fy\d*|fiscal|financial\s+year|"
    r"month|year to date|\bytd\b|"
    r"what year|which year|which fy"
    r")\b",
    re.I,
)


def _norm(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip().lower())


def is_clock_only(message: str) -> bool:
    text = _norm(message)
    if not text or _PERF.search(text):
        return False
    return bool(_CLOCK.search(text))


def _chat_result(answer: str) -> dict:
    return {
        "answer": answer,
        "cards": [],
        "sources": [],
        "metrics_used": [],
        "sqls": [],
    }


def clock_only_answer(message: str, clock: date) -> dict | None:
    if not is_clock_only(message):
        return None
    text = _norm(message)
    w = windows(clock)

    asked_last_q = bool(re.search(r"\b(last|previous|prior)\s+quarter\b", text))
    asked_next_q = bool(re.search(r"\bnext\s+quarter\b", text))
    asked_last_m = bool(re.search(r"\b(last|previous|prior)\s+month\b", text))
    asked_this_m = bool(
        re.search(r"\b(this|current)\s+month\b", text)
        or re.search(r"\b(what|which)\s+month\b", text)
    )
    asked_fy_q = bool(
        re.search(r"\b(quarter|q[1-4]|fy|fiscal|financial\s+year)\b", text)
    ) and not asked_last_q and not asked_next_q
    asked_date = bool(
        re.search(r"\b(today|tonight|date|clock|day)\b", text) or re.search(r"as[- ]of", text)
    )

    parts: list[str] = []
    if asked_date or not (asked_last_q or asked_next_q or asked_last_m or asked_this_m or asked_fy_q):
        parts.append(
            f"The demo clock is {w['clock_pretty']}. Treat that as today; "
            f"I ignore rows dated after {w['clock']}."
        )
    if asked_fy_q:
        parts.append(
            f"We are in {w['fiscal_quarter_label']} "
            f"({w['this_quarter_name']}: {w['this_quarter_start']} through {w['clock']}). "
            f"Fiscal year is the calendar year (1 January–31 December {w['fiscal_year']})."
        )
    if asked_last_q:
        parts.append(
            f"Last quarter was {w['last_quarter_name']} "
            f"({w['last_quarter_start']} through {w['last_quarter_end']})."
        )
    if asked_next_q:
        parts.append(
            f"Next quarter is {w['next_quarter_name']} "
            f"({w['next_quarter_start']} through {w['next_quarter_end']}), "
            f"used only for suggestions."
        )
    if asked_this_m:
        parts.append(
            f"This month is {w['this_month_name']} "
            f"({w['this_month_start']} through {w['clock']})."
        )
    if asked_last_m:
        parts.append(
            f"Last month was {w['last_month_name']} "
            f"({w['last_month_start']} through {w['last_month_end']})."
        )
    if asked_fy_q:
        parts.append(
            f"This financial year to date is {w['fiscal_year_start']} through {w['clock']}."
        )

    # Keep FY-to-date from duplicating when we already said FY quarter + date.
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return _chat_result(" ".join(seen))
