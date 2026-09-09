from __future__ import annotations

from datetime import date, timedelta


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _quarter_start(d: date) -> date:
    q = (d.month - 1) // 3
    return date(d.year, q * 3 + 1, 1)


def _quarter_num(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _pretty(d: date) -> str:
    return d.strftime("%d %B %Y").lstrip("0")


def windows(clock: date) -> dict[str, str]:
    this_month_start = _month_start(clock)
    last_month_start = _add_months(this_month_start, -1)
    last_month_end = this_month_start - timedelta(days=1)
    this_q_start = _quarter_start(clock)
    last_q_start = _add_months(this_q_start, -3)
    last_q_end = this_q_start - timedelta(days=1)
    next_q_start = _add_months(this_q_start, 3)
    next_q_end = _add_months(next_q_start, 3) - timedelta(days=1)
    t30_start = clock - timedelta(days=29)
    p30_start = clock - timedelta(days=59)
    p30_end = clock - timedelta(days=30)
    t90_start = clock - timedelta(days=89)
    p90_start = clock - timedelta(days=179)
    p90_end = clock - timedelta(days=90)
    t28_start = clock - timedelta(days=27)
    fy = clock.year
    fq = _quarter_num(clock)
    last_q = _quarter_num(last_q_start)
    next_q = _quarter_num(next_q_start)
    fy_start = date(fy, 1, 1)
    fy_end = date(fy, 12, 31)
    return {
        "clock": clock.isoformat(),
        "clock_pretty": _pretty(clock),
        "this_month_start": this_month_start.isoformat(),
        "this_month_name": clock.strftime("%B %Y"),
        "last_month_start": last_month_start.isoformat(),
        "last_month_end": last_month_end.isoformat(),
        "last_month_name": last_month_start.strftime("%B %Y"),
        "this_quarter_start": this_q_start.isoformat(),
        "this_quarter_name": f"Q{fq} {fy}",
        "last_quarter_start": last_q_start.isoformat(),
        "last_quarter_end": last_q_end.isoformat(),
        "last_quarter_name": f"Q{last_q} {last_q_start.year}",
        "next_quarter_start": next_q_start.isoformat(),
        "next_quarter_end": next_q_end.isoformat(),
        "next_quarter_name": f"Q{next_q} {next_q_start.year}",
        "fiscal_year": str(fy),
        "fiscal_quarter": str(fq),
        "fiscal_quarter_label": f"FY{fy} Q{fq}",
        "fiscal_year_start": fy_start.isoformat(),
        "fiscal_year_end": fy_end.isoformat(),
        "trailing_30_start": t30_start.isoformat(),
        "prior_30_start": p30_start.isoformat(),
        "prior_30_end": p30_end.isoformat(),
        "trailing_90_start": t90_start.isoformat(),
        "prior_90_start": p90_start.isoformat(),
        "prior_90_end": p90_end.isoformat(),
        "trailing_28_start": t28_start.isoformat(),
        "same_quarter_last_year_start": date(this_q_start.year - 1, this_q_start.month, 1).isoformat(),
    }


def prompt_windows(clock: date) -> str:
    w = windows(clock)
    return (
        f"Demo clock (treat as today): {w['clock']}\n"
        f"Ignore any row with a date after {w['clock']}.\n"
        f"Fiscal year = calendar year. {w['fiscal_quarter_label']} "
        f"({w['this_quarter_name']}) = {w['this_quarter_start']} to {w['clock']}.\n"
        f"This month ({w['this_month_name']}): {w['this_month_start']} to {w['clock']}\n"
        f"Last month ({w['last_month_name']}): {w['last_month_start']} to {w['last_month_end']}\n"
        f"This quarter ({w['this_quarter_name']}): {w['this_quarter_start']} to {w['clock']}\n"
        f"Last quarter ({w['last_quarter_name']}): {w['last_quarter_start']} to {w['last_quarter_end']}\n"
        f"This FY to date: {w['fiscal_year_start']} to {w['clock']} "
        f"(FY ends {w['fiscal_year_end']})\n"
        f"Trailing 30 days: {w['trailing_30_start']} to {w['clock']}\n"
        f"Prior 30 days: {w['prior_30_start']} to {w['prior_30_end']}\n"
        f"Trailing 90 days: {w['trailing_90_start']} to {w['clock']}\n"
        f"Next quarter (for suggestions only, {w['next_quarter_name']}): "
        f"{w['next_quarter_start']} to {w['next_quarter_end']}\n"
    )
