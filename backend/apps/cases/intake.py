"""Intake proposal builder; results are persisted only by the case worker."""

import re

from django.conf import settings
from rest_framework import serializers

from apps.llm import LLMError, complete_json

FIELDS = {
    "company_name": "Как называется компания?",
    "company_inn": "Какой ИНН указан у компании?",
    "amount": "Какую сумму вы оплатили?",
    "payment_date": "Когда вы оплатили услугу?",
    "payment_method": "Каким способом вы оплатили услугу?",
    "promised": "Что вам обещали?",
    "happened": "Что произошло?",
    "actions_taken": "Что вы уже предприняли?",
}

# Conservative signals only: moderation and an explicit emergency state remain
# necessary because a keyword list cannot recognize every dangerous situation.
EMERGENCY = re.compile(
    r"угрожа\w*|угроз\w*|"
    r"(?:мошенник\w*|мошенничеств\w*|списыва\w*|похища\w*|вору\w*)"
    r"[^.!?]{0,60}(?:прямо\s+сейчас|сейчас|в\s+эту\s+минуту)|"
    r"(?:прямо\s+сейчас|сейчас|в\s+эту\s+минуту|срочно)"
    r"[^.!?]{0,60}(?:мошенник\w*|мошенничеств\w*|списыва\w*|похища\w*|вору\w*)",
    re.IGNORECASE,
)
EMERGENCY_REPLY = (
    "Если вам угрожает непосредственная опасность, обратитесь в полицию по номеру 112. "
    "Если деньги списывают сейчас, немедленно свяжитесь с банком."
)


class ProposedFactSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=list(FIELDS))
    value = serializers.CharField(allow_blank=False)
    quote = serializers.CharField(allow_blank=False)
    source_index = serializers.IntegerField(min_value=0)


class ModelOutputSerializer(serializers.Serializer):
    facts = ProposedFactSerializer(many=True)
    urgent = serializers.BooleanField()
    category = serializers.CharField(allow_null=True)


def _sources(case):
    """Use only the current case's user messages and UTF-8 text documents."""
    result = [
        {
            "kind": "message",
            "id": str(message.pk),
            "source_version": 1,
            "text": message.text,
        }
        for message in case.messages.filter(author="user")
    ]
    for doc in case.documents.filter(content_type="text/plain").order_by("created_at", "id"):
        try:
            text = bytes(doc.content).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Invalid source encoding") from exc
        result.append(
            {
                "kind": "document",
                "id": str(doc.pk),
                "source_version": doc.source_version,
                "text": text,
            }
        )
    for index, source in enumerate(result):
        source["index"] = index
    return result


def _empty_fact(key):
    return {
        "key": key,
        "required": True,
        "status": "not_found",
        "value": None,
        "source": None,
        "source_quote": None,
    }


def next_step(case):
    """Build a proposal without changing the case or accepting foreign sources."""
    sources = _sources(case)
    if not sources:
        raise ValueError("No sources")

    if any(EMERGENCY.search(source["text"]) for source in sources):
        return {
            "questions": [EMERGENCY_REPLY],
            "missing_documents": [],
            "proposed_facts": [],
            "card_ready": False,
            "urgent": True,
            "category": None,
        }

    # The team's open Q-S1-05 forbids transmitting real case data to an LLM
    # until the consent and processing rules are resolved. No client-supplied
    # flag is sufficient evidence that a case is synthetic.
    if settings.LLM_PROVIDER != "mock":
        raise LLMError("Intake live provider is disabled pending data-transfer approval")

    message_count = sum(source["kind"] == "message" for source in sources)
    scenario = ("first", "second", "complete")[min(message_count, 3) - 1]
    response = complete_json(
        "intake", {"scenario": scenario, "sources": sources}, ModelOutputSerializer
    )
    if response["urgent"]:
        return {
            "questions": [EMERGENCY_REPLY],
            "missing_documents": [],
            "proposed_facts": [],
            "card_ready": False,
            "urgent": True,
            "category": response["category"],
        }
    facts = {key: _empty_fact(key) for key in FIELDS}
    for proposal in response["facts"]:
        key = proposal["key"]
        index = proposal["source_index"]
        if index >= len(sources):
            continue
        source = sources[index]
        quote = proposal["quote"]
        if not quote.strip() or quote not in source["text"] or proposal["value"] not in quote:
            continue
        facts[key] = {
            "key": key,
            "required": True,
            "status": "found",
            "value": proposal["value"],
            "source": {name: source[name] for name in ("kind", "id", "source_version")},
            "source_quote": quote,
        }

    missing = [key for key, fact in facts.items() if fact["status"] == "not_found"]
    # Uploaded documents have no trusted document-type field, so their presence
    # alone cannot prove that both the receipt and contract were supplied.
    missing_documents = [
        "Если ещё не приложили чек, добавьте его: он поможет подтвердить оплату.",
        "Если ещё не приложили договор, добавьте его: он поможет подтвердить условия.",
    ]
    if case.documents.filter(
        content_type__in=["image/png", "image/jpeg", "application/pdf"]
    ).exists():
        missing_documents.append(
            "Перепишите данные с фото или PDF текстом: такие файлы AI пока не читает."
        )
    return {
        "questions": [FIELDS[key] for key in missing[:5]],
        "missing_documents": missing_documents,
        "proposed_facts": list(facts.values()),
        "card_ready": not missing,
        "urgent": False,
        "category": response["category"],
    }
