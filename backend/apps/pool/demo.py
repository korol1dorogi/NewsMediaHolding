"""Demo data (D2): fictional cases about the demo company, a queue and a pool.

Everything is synthetic and owned by the demo account ``demo_crowd``. The demo company
uses the sentinel INN 0000000000, which is never sent to a real registry.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.cases.models import CardSnapshot, Case, Fact
from apps.claims.models import Claim, ClaimPersonalData, ClaimVersion

from . import services

CROWD = "demo_crowd"
TOTAL = 33
CITIES = ("Вымышленск", "Учебноград", "Демо-Сити", "Тестовск", "Примерово")
AMOUNTS = ("68000 рублей", "45000 рублей", "120000 рублей", "32000 рублей", "89000 рублей")
QUEUE = 3
POOL = 3


def _facts(index):
    return {
        "company_name": "Учебный проект Демо",
        "company_inn": "0000000000",
        "amount": AMOUNTS[index % len(AMOUNTS)],
        "payment_date": (timezone.localdate() - timedelta(days=20 + index * 3)).isoformat(),
        "payment_method": "банковской картой",
        "promised": "записанные уроки",
        "happened": "деньги не возвращают",
        "actions_taken": "написала претензию",
        "city": CITIES[index % len(CITIES)],
    }


def _case(owner, index, state, path=None):
    confirmed = timezone.now() - timedelta(days=index * 9)
    case = Case.objects.create(
        owner=owner,
        state=state,
        path=path,
        ai_state="idle",
        consent_text_version="demo-v1",
        card_confirmed_at=confirmed,
    )
    rows = []
    for key, value in _facts(index).items():
        Fact.objects.create(case=case, key=key, value=value, status="user_edited", required=True)
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
    CardSnapshot.objects.create(case=case, version=1, facts=rows, confirmed_at=confirmed)
    return case


def _queued_claim(case, index):
    from apps.guidance.drafting import draft_claim
    from apps.payments import services as payments
    from apps.payments.models import Purpose

    draft = draft_claim(case)
    claim = Claim.objects.create(
        case=case,
        card_version=1,
        current_version=1,
        norm_ids=draft["norm_ids"],
        personal_data_confirmed=True,
        submit_consent_version="demo-v1",
    )
    ClaimVersion.objects.create(
        claim=claim, version=1, author="ai", template_text=draft["template_text"]
    )
    ClaimPersonalData.objects.create(
        claim=claim,
        full_name=f"Демо Заявитель {index}",
        reply_address="Вымышленный город, учебный адрес",
        contract_reference=f"DEMO-{index:03d}",
        confirmed_at=timezone.now(),
    )
    claim.hold = payments.hold(
        case.owner, Purpose.CLAIM_REVIEW, claim.pk, 149_000, f"demo-claim-{claim.pk}"
    )
    claim.submitted_at = claim.queued_at = timezone.now() - timedelta(hours=index)
    claim.save()


def seed():
    """Idempotent: does nothing if the demo crowd already has its cases."""
    user_model = get_user_model()
    owner, _ = user_model.objects.get_or_create(
        username=CROWD, defaults={"role": "user", "is_demo": True}
    )
    if not owner.is_demo:
        raise ValueError("demo_crowd is occupied by a non-demo account")
    if owner.has_usable_password():
        owner.set_unusable_password()  # nobody signs in as the crowd
        owner.save(update_fields=["password"])
    if Case.objects.filter(owner=owner).count() >= TOTAL:
        return False
    for index in range(TOTAL):
        if index < QUEUE:
            _queued_claim(_case(owner, index, "claim_in_review", "claim"), index)
        elif index < QUEUE + POOL:
            case = _case(owner, index, "in_pool", "specialist")
            card, _ = services.publish(case)
            services.approve(card)
        else:
            _case(owner, index, "self_guided", "self_guided")
    return True
