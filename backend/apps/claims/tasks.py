from functools import partial

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.cases.models import Case
from apps.guidance.drafting import draft_claim

from .models import Claim, ClaimVersion


def pending(case_id, version):
    return Case.objects.filter(
        pk=case_id, version=version, state="claim_draft", ai_state="thinking"
    )


def fail(case_id, version):
    pending(case_id, version).update(
        ai_state="failed", version=F("version") + 1, updated_at=timezone.now()
    )


@shared_task(ignore_result=True)
def make_draft(case_id, version):
    case = pending(case_id, version).first()
    if case is None:
        return
    try:
        result = draft_claim(case)
    except Exception:
        # Errors can carry private card text; persist only the outcome.
        fail(case_id, version)
        return
    with transaction.atomic():
        case = pending(case_id, version).select_for_update().first()
        if case is None or result["input_card_version"] != case.card_snapshot.version:
            return
        claim = Claim.objects.select_for_update().get(case=case)
        if claim.ready:
            return
        ClaimVersion.objects.create(
            claim=claim,
            version=1,
            author=ClaimVersion.Author.AI,
            template_text=result["template_text"],
        )
        claim.current_version = 1
        claim.card_version = result["input_card_version"]
        claim.norm_ids = result["norm_ids"]
        claim.save(update_fields=["current_version", "card_version", "norm_ids"])
        case.ai_state = "idle"
        case.version += 1
        case.save()


def _enqueue(case_id, version):
    try:
        make_draft.delay(case_id, version)
    except OperationalError:
        fail(case_id, version)


def schedule(case):
    transaction.on_commit(partial(_enqueue, str(case.pk), case.version))
