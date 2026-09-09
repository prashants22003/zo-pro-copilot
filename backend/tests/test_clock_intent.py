from datetime import date

import pytest

from app.clock import prompt_windows, windows
from app.clock_intent import clock_only_answer, is_clock_only

CLOCK = date(2015, 9, 14)

MUST_SHORT = [
    "Which fy quarter we are in?",
    "Which FY quarter are we in?",
    "what financial year is this",
    "what quarter are we in",
    "what date is it",
    "what's today",
    "what is the demo clock",
    "as of when",
    "what month is it",
    "what is last quarter",
    "when is last month",
    "what is next quarter",
]

MUST_NOT = [
    "How did last quarter look?",
    "how did we do in Q2?",
    "how did we perform last quarter",
    "sales this quarter",
    "revenue last month",
    "which region grew last quarter",
    "overdue purchase orders",
    "stock on hand today",
    "top customers this FY",
    "how did Q2 look",
]


@pytest.mark.parametrize("utterance", MUST_SHORT)
def test_clock_only_true(utterance: str) -> None:
    assert is_clock_only(utterance), utterance


@pytest.mark.parametrize("utterance", MUST_NOT)
def test_clock_only_false(utterance: str) -> None:
    assert not is_clock_only(utterance), utterance


def test_windows_fy_labels() -> None:
    w = windows(CLOCK)
    assert w["fiscal_year"] == "2015"
    assert w["fiscal_quarter"] == "3"
    assert w["fiscal_quarter_label"] == "FY2015 Q3"
    assert w["this_quarter_name"] == "Q3 2015"
    assert w["this_quarter_start"] == "2015-07-01"
    assert w["last_quarter_name"] == "Q2 2015"
    assert w["last_quarter_start"] == "2015-04-01"
    assert w["last_quarter_end"] == "2015-06-30"
    assert w["fiscal_year_start"] == "2015-01-01"
    assert w["fiscal_year_end"] == "2015-12-31"
    assert w["this_month_name"] == "September 2015"


def test_fy_quarter_answer() -> None:
    hit = clock_only_answer("Which fy quarter we are in?", CLOCK)
    assert hit is not None
    assert hit["cards"] == []
    assert hit["sqls"] == []
    assert "FY2015 Q3" in hit["answer"]
    assert "2015-07-01" in hit["answer"]


def test_performance_question_not_answered() -> None:
    assert clock_only_answer("How did last quarter look?", CLOCK) is None
    assert clock_only_answer("how did we do in Q2?", CLOCK) is None


def test_prompt_windows_includes_fy() -> None:
    text = prompt_windows(CLOCK)
    assert "FY2015 Q3" in text
    assert "2015-07-01" in text
