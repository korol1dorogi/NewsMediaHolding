from .facts import AMOUNT, COMPANY_INN, COMPANY_NAME, PAYMENT_DATE, SERVICE_DESCRIPTION

# Demo phrases the stub recognises verbatim; everything else is left for the user to fill in.
_SAMPLES = (
    (AMOUNT, "68 000 ₽", True),
    (COMPANY_INN, "0000000000", True),
    (COMPANY_NAME, "Учебный проект Демо", True),
    (PAYMENT_DATE, "1 октября", True),
    (SERVICE_DESCRIPTION, "онлайн-курс", False),
)


def next_step(case):
    """Deterministic intake until A2 supplies its implementation.

    Proposes every card key (apps.cases.facts); a key is ``found`` only when its demo
    phrase is quoted verbatim from a user message, so the card can be completed by hand.
    """
    ready = case.messages.filter(author="user").count() >= 2
    facts = []
    if ready:
        for key, sample, required in _SAMPLES:
            message = case.messages.filter(author="user", text__contains=sample).first()
            facts.append(
                {
                    "key": key,
                    "required": required,
                    "status": "found" if message else "not_found",
                    "value": sample if message else None,
                    "source_quote": sample if message else None,
                    "source": {"kind": "message", "id": str(message.pk), "source_version": 1}
                    if message
                    else None,
                }
            )
    return {
        "questions": [] if ready else ["Когда вы оплатили услугу и что вам обещали?"],
        "missing_documents": [],
        "proposed_facts": facts,
        "card_ready": ready,
    }
