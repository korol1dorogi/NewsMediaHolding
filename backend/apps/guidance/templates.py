"""Deterministic, unverified document drafts from explicitly supplied facts.

These internal names are inputs to this library, not fields of a public API.
Personal placeholders are proposals; their identifiers and
processing are not yet approved for integration. Free-text facts can contain
personal data: the resulting draft must not be exposed to the lawyer queue until
an independent safe-redaction process has been verified. Requirements and text
have not been reviewed by a lawyer.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from string import Template
from unicodedata import category

_ROOT = Path(__file__).parent / "resources" / "templates"
_FIELDS = {
    "claim": {
        "company_name",
        "service_description",
        "payment_date",
        "amount_kopecks",
        "claim_amount_kopecks",
        "circumstances",
    },
    "bank": {
        "bank_name",
        "merchant_name",
        "transaction_date",
        "amount_kopecks",
        "circumstances",
        "request",
    },
    "consumer_authority": {
        "authority_name",
        "company_name",
        "service_description",
        "payment_date",
        "amount_kopecks",
        "claim_date",
        "circumstances",
        "request",
    },
}
_DATES = {"payment_date", "transaction_date", "claim_date"}
_MONEY = {"amount_kopecks", "claim_amount_kopecks"}
_FORBIDDEN = ("{{", "}}", "{%", "%}", "{#", "#}", "${", "<%", "%>")


@dataclass(frozen=True)
class DocumentDraft:
    template_text: str
    verified_by_lawyer: bool = False


class MissingFacts(ValueError):
    """Expose only required field names, never submitted values."""

    def __init__(self, names):
        self.names = tuple(sorted(names))
        super().__init__("Required facts missing: " + ", ".join(self.names))


class InvalidFact(ValueError):
    """Expose only the relevant field name, never the submitted value."""

    def __init__(self, name):
        self.name = name
        super().__init__("Invalid fact: " + name)


def required_fields(kind):
    """Internal draft requirements, subject to legal review."""
    if kind not in _FIELDS:
        raise ValueError("Unknown document type")
    return frozenset(_FIELDS[kind])


def _value(name, value):
    if name in _MONEY:
        if type(value) is not int or value <= 0:
            raise InvalidFact(name)
        return f"{value // 100}.{value % 100:02d}"
    if name in _DATES:
        try:
            if type(value) is not str:
                raise ValueError
            return date.fromisoformat(value).strftime("%d.%m.%Y")
        except ValueError:
            raise InvalidFact(name) from None
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 2000
        or any(category(char).startswith("C") for char in value)
        or any(token in value for token in _FORBIDDEN)
    ):
        raise InvalidFact(name)
    return value.strip()


def render_document(kind, facts):
    """Render one draft once; missing and untrusted fields fail closed.

    Explicit personal-data fields are rejected; free-text facts may nevertheless
    contain personal data. Placeholder names are proposed and not yet approved
    for integration. Do not log returned text or expose it to the lawyer queue
    before verified independent redaction.
    """
    fields = required_fields(kind)
    if not isinstance(facts, dict):
        raise ValueError("Facts must be a mapping")
    if set(facts) - fields:
        raise ValueError("Unexpected fact fields")
    missing = [name for name in fields if facts.get(name) in (None, "")]
    if missing:
        raise MissingFacts(missing)
    values = {name: _value(name, facts[name]) for name in fields}
    if "amount_kopecks" in values:
        values["amount_rub"] = values.pop("amount_kopecks")
    if "claim_amount_kopecks" in values:
        values["claim_amount_rub"] = values.pop("claim_amount_kopecks")
    source = (_ROOT / f"{kind}.txt").read_text(encoding="utf-8")
    return DocumentDraft(Template(source).substitute(values))
