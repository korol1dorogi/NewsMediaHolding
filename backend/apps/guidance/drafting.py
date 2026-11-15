"""guidance.draft_claim(case) (A4): the model writes prose, code writes everything else.

The model returns only the description of circumstances. Company, amounts, dates and the
norms block are filled in by code from the confirmed card and the A3 library. The model
text is rejected if it cites legal provisions, promises an outcome or contains numbers
that are not on the card.
"""

import re

from django.conf import settings
from rest_framework import serializers

from apps.cases.facts import (
    AMOUNT,
    COMPANY_NAME,
    HAPPENED,
    PAYMENT_DATE,
    PROMISED,
    SERVICE_DESCRIPTION,
    confirmed_values,
    parse_amount,
    parse_date,
    service_text,
)
from apps.llm.client import LLMError, complete_json

from .plan import claim_norms
from .templates import InvalidFact, MissingFacts, render_document

REQUIRED_FACTS = (COMPANY_NAME, PAYMENT_DATE, AMOUNT)
DEFAULT_SERVICE = "оплаченная услуга"

_LEGAL_REFERENCE = re.compile(
    r"(стать[яиеюей]\w*|\bст\.|\bч\.\s*\d|\bп\.\s*\d|пункт\w*\s+\d|закон\w*|кодекс\w*|"
    r"\bгк\b|\bгпк\b|\bкоап\b|зозпп|постановлени\w*|article|§)",
    re.IGNORECASE,
)
_PROMISE = re.compile(
    r"(гарантир\w*|обязательно\s+(?:вернут|выиграе|получите)|100\s*%|"
    r"точно\s+(?:вернут|выиграе)|без\s+сомнени)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d\s.,]*\d|\d")


class DraftError(Exception):
    """The draft could not be produced; message has no user data."""


class UnconfirmedCard(DraftError):
    pass


class InvalidOutput(DraftError):
    pass


class _ClaimText(serializers.Serializer):
    circumstances = serializers.CharField(min_length=20, max_length=1500)


def missing_facts(case):
    facts = confirmed_values(case)
    missing = [key for key in REQUIRED_FACTS if not facts.get(key)]
    if facts.get(AMOUNT) and parse_amount(facts[AMOUNT]) is None:
        missing.append(AMOUNT)
    if facts.get(PAYMENT_DATE) and not parse_date(
        facts[PAYMENT_DATE], today=case.created_at.date()
    ):
        missing.append(PAYMENT_DATE)
    return sorted(set(missing))


def _allowed_numbers(amount, paid_on):
    rubles = amount // 100
    return {
        str(rubles),
        f"{rubles},{amount % 100:02d}",
        f"{rubles}.{amount % 100:02d}",
        str(paid_on.day),
        f"{paid_on.day:02d}",
        str(paid_on.year),
        paid_on.strftime("%d.%m.%Y"),
        paid_on.isoformat(),
    }


def check_text(text, allowed_numbers):
    """Raise InvalidOutput if model prose breaks the rules. Returns the stripped text."""
    if _LEGAL_REFERENCE.search(text):
        raise InvalidOutput("Model text cites legal provisions")
    if _PROMISE.search(text):
        raise InvalidOutput("Model text promises an outcome")
    for token in _NUMBER.findall(text):
        normalized = re.sub(r"\s+", "", token).strip(".,")
        if normalized not in allowed_numbers:
            raise InvalidOutput("Model text contains a number that is not on the card")
    return text.strip().rstrip(".")


def _norms_block(norms):
    if not norms:
        return ""
    lines = [f"— {norm['article']}: {norm['title']}" for norm in norms]
    return "\n\nПравовые основания (из библиотеки, не проверено юристом):\n" + "\n".join(lines)


def draft_claim(case):
    """Return DraftClaimResult: input_card_version, template_text, norm_ids."""
    if case.card_confirmed_at is None:
        raise UnconfirmedCard("Card is not confirmed")
    missing = missing_facts(case)
    if missing:
        raise MissingFacts(missing)
    facts = confirmed_values(case)
    amount = parse_amount(facts[AMOUNT])
    paid_on = parse_date(facts[PAYMENT_DATE], today=case.created_at.date())
    allowed = _allowed_numbers(amount, paid_on)
    payload = {
        "scenario": settings.LLM_MOCK_SCENARIO,
        "instruction": (
            "Опиши обстоятельства для досудебной претензии: что было оплачено и что пошло не "
            "так. Только факты из data.facts. Без сумм, дат, ссылок на законы и обещаний."
        ),
        "facts": {
            key: facts[key]
            for key in (COMPANY_NAME, SERVICE_DESCRIPTION, PROMISED, HAPPENED, PAYMENT_DATE, AMOUNT)
            if key in facts
        },
    }
    circumstances = None
    for _attempt in range(2):
        try:
            result = complete_json("draft_claim", payload, _ClaimText)
            circumstances = check_text(result["circumstances"], allowed)
            break
        except (LLMError, InvalidOutput):
            continue
    if circumstances is None:
        raise InvalidOutput("No valid draft after retry")

    norms = claim_norms(case)
    try:
        draft = render_document(
            "claim",
            {
                "company_name": facts[COMPANY_NAME],
                "service_description": service_text(facts) or DEFAULT_SERVICE,
                "payment_date": paid_on.isoformat(),
                "amount_kopecks": amount,
                "claim_amount_kopecks": amount,
                "circumstances": circumstances,
            },
        )
    except InvalidFact as exc:
        raise MissingFacts([exc.name]) from None
    return {
        "input_card_version": case.card_snapshot.version,
        "template_text": draft.template_text + _norms_block(norms),
        "norm_ids": [norm["id"] for norm in norms],
    }
