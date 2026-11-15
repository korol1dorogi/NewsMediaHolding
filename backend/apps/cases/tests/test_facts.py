from datetime import date

import pytest

from apps.cases.facts import format_rub, parse_amount, parse_date

TODAY = date(2026, 11, 15)


@pytest.mark.parametrize(
    ("text", "kopecks"),
    [
        ("68 000 ₽", 6_800_000),
        ("68000", 6_800_000),
        ("68 000 руб.", 6_800_000),
        ("1 490 рублей", 149_000),
        ("1490,5", 149_050),
        ("1490.05", 149_005),
    ],
)
def test_parse_amount(text, kopecks):
    assert parse_amount(text) == kopecks


@pytest.mark.parametrize("text", ["", "много", "0", "-5", "12e3", "68 000 $", None, 68000])
def test_parse_amount_rejects(text):
    assert parse_amount(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-01", date(2026, 10, 1)),
        ("01.10.2026", date(2026, 10, 1)),
        ("1 октября 2026", date(2026, 10, 1)),
        ("1 октября 2026 г.", date(2026, 10, 1)),
        ("1 октября", date(2026, 10, 1)),
        ("3 мая", date(2026, 5, 3)),
        # A day-month in the future means the previous year.
        ("20 декабря", date(2025, 12, 20)),
        ("15 ноября", date(2026, 11, 15)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text, today=TODAY) == expected


@pytest.mark.parametrize("text", ["вчера", "31.02.2026", "1 мартобря", "32 октября", "", None])
def test_parse_date_rejects(text):
    assert parse_date(text, today=TODAY) is None


def test_format_rub():
    assert format_rub(6_800_000) == "68 000 ₽"
    assert format_rub(149_050) == "1 490,50 ₽"
