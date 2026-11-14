def next_step(case):
    """Deterministic intake until A2 supplies its implementation."""
    ready = case.messages.filter(author="user").count() >= 2
    return {
        "questions": [] if ready else ["Когда вы оплатили услугу и что вам обещали?"],
        "missing_documents": [],
        "proposed_facts": [],
        "card_ready": ready,
    }
