"""Test helpers shared by apps that start from a confirmed card. Synthetic data only."""

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import CardSnapshot, Case, Fact

ANYA_FACTS = {
    "company_name": "Учебный проект Демо",
    "company_inn": "0000000000",
    "service_description": "онлайн-курс по программированию",
    "payment_date": "2026-10-01",
    "amount": "68 000 ₽",
}


def make_user(username, role="user"):
    return get_user_model().objects.create_user(username=username, password=None, role=role)


def confirmed_case(owner, facts=None, *, state="card_confirmed"):
    facts = ANYA_FACTS if facts is None else facts
    case = Case.objects.create(
        owner=owner,
        state=state,
        ai_state="idle",
        consent_text_version="v1",
        card_confirmed_at=timezone.now(),
    )
    rows = []
    for key, value in facts.items():
        Fact.objects.create(
            case=case, key=key, value=value, status=Fact.Status.USER_EDITED, required=True
        )
        rows.append(
            {
                "key": key,
                "required": True,
                "value": value,
                "status": "user_edited",
                "source": None,
                "source_quote": None,
            }
        )
    CardSnapshot.objects.create(
        case=case, version=case.card_version, facts=rows, confirmed_at=case.card_confirmed_at
    )
    return case
