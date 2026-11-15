def next_step(case):
    """Deterministic intake until A2 supplies its implementation."""
    ready = case.messages.filter(author="user").count() >= 2
    facts = []
    if ready:
        for key, sample in (("company_name", "Учебный проект Демо"), ("payment_date", "1 октября")):
            message = case.messages.filter(author="user", text__contains=sample).first()
            facts.append(
                {
                    "key": key,
                    "required": True,
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
