"""Card fact keys shared by intake, guidance and claims, and code-side value parsing.

Fact values are free text confirmed by the user. Amounts and dates used in plans and
claims are parsed here by code, never taken from a model.
"""

import re
from datetime import date

COMPANY_NAME = "company_name"
COMPANY_INN = "company_inn"
SERVICE_DESCRIPTION = "service_description"
PAYMENT_DATE = "payment_date"
AMOUNT = "amount"
# Keys proposed by A2 intake (backend/apps/cases/intake.py).
PAYMENT_METHOD = "payment_method"
PROMISED = "promised"
HAPPENED = "happened"
ACTIONS_TAKEN = "actions_taken"
# Optional, filled by the user; used for the pool card and «Вы не один».
CITY = "city"

KNOWN_KEYS = (
    COMPANY_NAME,
    COMPANY_INN,
    SERVICE_DESCRIPTION,
    PAYMENT_DATE,
    AMOUNT,
    PAYMENT_METHOD,
    PROMISED,
    HAPPENED,
    ACTIONS_TAKEN,
    CITY,
)


def service_text(facts):
    """What was paid for: the explicit description, otherwise what was promised (A2)."""
    return facts.get(SERVICE_DESCRIPTION) or facts.get(PROMISED)


_MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
_TEXT_DATE = re.compile(r"^(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?(?:\s*г(?:ода|\.)?)?$")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_AMOUNT = re.compile(r"^(\d+)(?:[.,](\d{1,2}))?$")
_CURRENCY = re.compile(r"(₽|руб(?:лей|ля|ль)?\.?|р\.)$")


def confirmed_values(case):
    """Values from the confirmed snapshot only; an unconfirmed card has no usable facts."""
    snapshot = getattr(case, "card_snapshot", None) if case.card_confirmed_at else None
    if snapshot is None:
        return {}
    return {
        row["key"]: row["value"].strip()
        for row in snapshot.facts
        if isinstance(row.get("value"), str) and row["value"].strip()
    }


def parse_amount(value):
    """'68 000 ₽', '68000,50', '1 490 руб.' -> kopecks; anything else -> None."""
    if not isinstance(value, str):
        return None
    text = value.lower().replace(" ", " ").replace(" ", " ").strip()
    text = _CURRENCY.sub("", text).strip().replace(" ", "")
    match = _AMOUNT.match(text)
    if not match:
        return None
    kopecks = int(match.group(1)) * 100 + int((match.group(2) or "0").ljust(2, "0"))
    return kopecks if kopecks > 0 else None


def _month(word):
    """Accept only real month forms: 'октября', 'октябрь', 'мая', 'март', not 'мартобря'."""
    for stem, number in _MONTHS.items():
        if stem == "ма":
            if word in {"мая", "май"}:
                return number
        elif word.startswith(stem) and word[len(stem) :] in {"", "а", "я", "ь"}:
            return number
    return None


def parse_date(value, *, today):
    """ISO, 'DD.MM.YYYY', '1 октября 2026', '1 октября' -> date; else None.

    A date without a year is the latest such date not after ``today`` (the day the
    case was created): people describe recent payments without the year.
    """
    if not isinstance(value, str):
        return None
    text = value.lower().replace(" ", " ").strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        if match := _NUMERIC_DATE.match(text):
            day, month, year = (int(group) for group in match.groups())
            return date(year, month, day)
        if match := _TEXT_DATE.match(text):
            month = _month(match.group(2))
            if month is None:
                return None
            day = int(match.group(1))
            if match.group(3):
                return date(int(match.group(3)), month, day)
            result = date(today.year, month, day)
            return result if result <= today else date(today.year - 1, month, day)
    except ValueError:
        return None
    return None


def format_rub(kopecks):
    rubles, rest = divmod(kopecks, 100)
    text = f"{rubles:,}".replace(",", " ")
    return f"{text},{rest:02d} ₽" if rest else f"{text} ₽"
