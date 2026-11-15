"""Deterministic checks for personal information in a public pool description.

A finding prevents publication. Detection is deliberately conservative and is
not a substitute for the required human moderation. Neither text nor matching
values are logged or returned; offsets identify the suspect portion to callers
that already have access to the source text.
"""

import re
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class KnownPersonalData:
    """Known confirmed values; never log or include them in representations."""

    names: tuple[str, ...] = field(default=(), repr=False)
    addresses: tuple[str, ...] = field(default=(), repr=False)
    contract_numbers: tuple[str, ...] = field(default=(), repr=False)
    passport_numbers: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True, order=True)
class Finding:
    kind: str
    start: int
    end: int


# Boundaries use Unicode word characters to avoid matching inside another token.
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])", re.I)
_PHONE = re.compile(
    r"(?<!\w)(?:(?:\+7|7|8)[\s().-]*\d{3}|9\d{2})"
    r"[\s().-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_NUMERIC_DATE = re.compile(r"(?<!\d)(?:\d{1,2}([./-])\d{1,2}\1\d{4}|\d{4}-\d{1,2}-\d{1,2})(?!\d)")
_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
_WORD_DATE = re.compile(
    r"(?<!\w)\d{1,2}\s+(?:" + "|".join(_MONTHS) + r")\s+\d{4}(?:\s*г(?:ода|\.)?)?(?!\w)",
    re.I,
)
_CONTRACT = re.compile(
    r"\b(?:(?:договор(?:а|у|ом|е)?|контракт(?:а|у|ом|е)?)\s*"
    r"(?:(?:№|номер(?:а|у|ом|е)?|#|n|от)\s*)?"
    r"|номер(?:а|у|ом|е)?\s+(?:договора|контракта)\s*(?:№|#|n)?\s*)"
    r"(?=[\w/-]*\d)[\w/-]+",
    re.I,
)
_PASSPORT = re.compile(
    r"\bпаспорт(?:а|у|ом|е)?\s*(?:(?:серия|№|номер)\s*)?\d{2}\s?\d{2}"
    r"\s*(?:№|номер)?\s*\d{6}(?!\d)",
    re.I,
)
_ADDRESS = re.compile(
    r"(?<!\w)(?:ул\.|улица|улице|улицы|проспект|пр-т|пр\.|проспекте|"
    r"переулок|пер\.|набережная|шоссе|бульвар|бул\.)\s*"
    r"[\wёЁ.-]+(?:\s+[\wёЁ.-]+){0,2}\s*,?\s*"
    r"(?:д(?:ом)?\.?\s*\d+[\w/-]*|\d+[\w/-]*)(?!\w)",
    re.I,
)
_APARTMENT = re.compile(
    r"(?<!\w)(?:кв\.|квартира|квартире|квартиры)\s*(?:№|#)?\s*\d+[\w/-]*(?!\w)",
    re.I,
)
_CASE_ENDINGS = (
    "",
    "а",
    "я",
    "у",
    "ю",
    "ы",
    "и",
    "е",
    "о",
    "ом",
    "ем",
    "ой",
    "ей",
    "ым",
    "им",
    "ых",
    "их",
    "ая",
    "яя",
    "ую",
    "юю",
    "ого",
    "его",
    "ому",
    "ему",
    "ою",
    "ею",
)


def _name_pattern(word: str) -> re.Pattern[str] | None:
    # The short stem is never matched on its own: that would block ordinary text.
    normalized = word.strip()
    if len(normalized) < 4 or not normalized.isalpha():
        return None
    # Adjectival surnames change the whole -ий/-ая ending, not one letter.
    # Keep singular case endings explicit; this is not general morphology.
    if normalized.lower().endswith(("ский", "ская")):
        base = normalized[:-2]
        case_endings = (
            ("ий", "ого", "ому", "им", "ом")
            if normalized.lower().endswith("ский")
            else ("ая", "ой", "ую", "ою")
        )
        endings = "|".join(re.escape(item) for item in case_endings)
        return re.compile(rf"(?<!\w){re.escape(base)}(?:{endings})(?!\w)", re.I)
    base = normalized[:-1] if normalized[-1].lower() in "аяийь" else normalized
    if len(base) < 3:
        return None
    endings = "|".join(re.escape(item) for item in sorted(_CASE_ENDINGS, key=len, reverse=True))
    return re.compile(rf"(?<!\w){re.escape(base)}(?:{endings})(?!\w)", re.I)


def _literal_pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(value.strip()) + r"(?!\w)", re.I)


def scan(text: str, personal_data: KnownPersonalData) -> list[Finding]:
    """Return suspicious spans; an empty list alone never authorizes publication.

    Known values must be supplied by the trusted caller, not inferred from the
    public text. Invalid inputs fail closed via ValueError. This is a heuristic
    detector; variants beyond its patterns still require human moderation.
    """
    if not isinstance(text, str) or not isinstance(personal_data, KnownPersonalData):
        raise ValueError("Invalid scanner input")
    patterns = [
        ("email", _EMAIL),
        ("phone", _PHONE),
        ("card", _CARD),
        ("date", _NUMERIC_DATE),
        ("date", _WORD_DATE),
        ("contract", _CONTRACT),
        ("passport", _PASSPORT),
        ("address", _ADDRESS),
        ("address", _APARTMENT),
    ]
    for values in (
        personal_data.names,
        personal_data.addresses,
        personal_data.contract_numbers,
        personal_data.passport_numbers,
    ):
        if not isinstance(values, tuple) or any(
            not isinstance(v, str) or not v.strip() for v in values
        ):
            raise ValueError("Invalid known personal data")
    for name in personal_data.names:
        words = re.findall(r"[^\W\d_]+", name, re.UNICODE)
        if not words or any(_name_pattern(word) is None for word in words):
            raise ValueError("Unsupported known name")
        patterns.extend(("name", _name_pattern(word)) for word in words)
    for kind, values in (
        ("address", personal_data.addresses),
        ("contract", personal_data.contract_numbers),
        ("passport", personal_data.passport_numbers),
    ):
        patterns.extend((kind, _literal_pattern(value)) for value in values)
    findings = set()
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            findings.add(Finding(kind, match.start(), match.end()))
    return sorted(findings, key=lambda finding: (finding.start, finding.end, finding.kind))


def date_to_month(value: str) -> str:
    """Convert a full date to YYYY-MM, rejecting ambiguous or invalid formats."""
    if not isinstance(value, str):
        raise ValueError("Invalid date")
    value = value.strip()
    try:
        iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
        day_first = re.fullmatch(r"(\d{1,2})([./-])(\d{1,2})\2(\d{4})", value)
        if iso:
            parsed = date(int(iso[1]), int(iso[2]), int(iso[3]))
        elif day_first:
            parsed = date(int(day_first[4]), int(day_first[3]), int(day_first[1]))
        else:
            match = re.fullmatch(
                r"(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})(?:\s*г(?:ода|\.)?)?",
                value,
                re.I,
            )
            if not match:
                raise ValueError("Unsupported date")
            parsed = date(int(match[3]), _MONTHS[match[2].lower()], int(match[1]))
    except (ValueError, OverflowError):
        raise ValueError("Invalid or unsupported date") from None
    return f"{parsed.year:04d}-{parsed.month:02d}"


def amount_range(amount_kopecks: int) -> dict[str, int]:
    """Return non-overlapping inclusive bounds in kopecks for a non-negative amount.

    Boundary amounts start the higher range. Above one million rubles, ranges
    have a width of one million rubles; no floats or exact amount are returned.
    """
    if (
        isinstance(amount_kopecks, bool)
        or not isinstance(amount_kopecks, int)
        or amount_kopecks < 0
    ):
        raise ValueError("Invalid amount")
    thresholds = (0, 1_000_000, 5_000_000, 10_000_000, 50_000_000, 100_000_000)
    for low, high in zip(thresholds, thresholds[1:], strict=False):
        if amount_kopecks < high:
            return {"min_kopecks": low, "max_kopecks": high - 1}
    step = 100_000_000
    low = amount_kopecks // step * step
    return {"min_kopecks": low, "max_kopecks": low + step - 1}
