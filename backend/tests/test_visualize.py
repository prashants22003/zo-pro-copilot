from app.visualize import present


def test_single_row_kpis_no_chart() -> None:
    viz = present([{"line_profit": 2112629.5, "revenue": 4824617.67}])
    assert viz["chart"] is None
    labels = {k["label"] for k in viz["kpis"]}
    assert "line profit" in labels
    assert "revenue" in labels


def test_monthly_is_line() -> None:
    viz = present(
        [
            {"month": "2015-01-01", "extended_price": 100.0},
            {"month": "2015-02-01", "extended_price": 200.0},
            {"month": "2015-03-01", "extended_price": 150.0},
        ]
    )
    assert viz["chart"]["type"] == "line"
    assert viz["chart"]["values"] == [100.0, 200.0, 150.0]


def test_share_is_pie() -> None:
    viz = present(
        [
            {"region": "North", "share": 0.4},
            {"region": "South", "share": 0.35},
            {"region": "East", "share": 0.25},
        ]
    )
    assert viz["chart"]["type"] == "pie"


def test_ranking_is_bar() -> None:
    viz = present(
        [
            {"customer_name": "A", "invoiced_value": 10},
            {"customer_name": "B", "invoiced_value": 50},
            {"customer_name": "C", "invoiced_value": 20},
            {"customer_name": "D", "invoiced_value": 5},
            {"customer_name": "E", "invoiced_value": 8},
            {"customer_name": "F", "invoiced_value": 12},
            {"customer_name": "G", "invoiced_value": 9},
            {"customer_name": "H", "invoiced_value": 7},
            {"customer_name": "I", "invoiced_value": 6},
        ]
    )
    assert viz["chart"]["type"] in {"bar", "hbar"}
    assert viz["flagged_row_indexes"][0] == 1


def test_negatives_not_pie() -> None:
    viz = present(
        [
            {"customer_name": "A", "pct": -0.4},
            {"customer_name": "B", "pct": 0.2},
            {"customer_name": "C", "pct": 0.1},
        ]
    )
    assert viz["chart"]["type"] != "pie"


def test_long_names_are_horizontal() -> None:
    viz = present(
        [
            {"customer_name": "Tailspin Toys (Head Office)", "invoiced_value": 10},
            {"customer_name": "Wingtip Toys (San Francisco)", "invoiced_value": 40},
            {"customer_name": "Contoso Warehouse North America", "invoiced_value": 20},
        ]
    )
    assert viz["chart"]["type"] == "hbar"


def test_few_categories_without_share_are_bar() -> None:
    viz = present(
        [
            {"region": "North", "revenue": 40},
            {"region": "South", "revenue": 35},
            {"region": "East", "revenue": 25},
        ]
    )
    assert viz["chart"]["type"] == "bar"


def test_prefers_name_and_matches_subject() -> None:
    viz = present(
        [
            {"subject_key": "194", "customer_name": "Tailspin Toys (Naples Park, FL)", "t30": 0.0, "p30": 40000.0},
            {"subject_key": "82", "customer_name": "Wingtip Toys (San Francisco)", "t30": 12000.0, "p30": 20000.0},
            {"subject_key": "81", "customer_name": "Contoso Warehouse North America", "t30": 8000.0, "p30": 15000.0},
        ],
        subject_key="customer:194",
    )
    assert viz["chart"]["type"] == "hbar"
    assert "Tailspin" in viz["chart"]["labels"][0]
    assert viz["flagged_row_indexes"][0] == 0
    assert viz["chart"]["series"][0]["name"] == "prior 30 days"


def test_empty() -> None:
    viz = present([])
    assert viz["chart"] is None
    assert viz["kpis"] == []
