from functools import partial

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from kombu.exceptions import OperationalError

from . import intake
from .models import Case, Message
from .states import transition


def pending(case_id, version):
    return Case.objects.filter(pk=case_id, version=version, state="draft", ai_state="thinking")


def fail(case_id, version):
    pending(case_id, version).update(
        ai_state="failed", version=F("version") + 1, updated_at=timezone.now()
    )


@shared_task(ignore_result=True)
def process_message(case_id, version):
    case = pending(case_id, version).first()
    if case is None:
        return
    try:
        result = intake.next_step(case)
        ready = result["card_ready"]
        reply = "Карточка готова к проверке." if ready else "\n".join(result["questions"])
        if not reply:
            raise ValueError("Missing intake response")
    except Exception:
        # Provider errors can contain private input; persist only the outcome.
        fail(case_id, version)
        return

    with transaction.atomic():
        case = pending(case_id, version).select_for_update().first()
        if case is None:
            return
        transition(case, "card_ready" if ready else "clarifying")
        Message.objects.create(case=case, author="ai", text=reply)
        case.ai_state = "idle"
        case.version += 1
        case.save()


def _enqueue(case_id, version):
    try:
        process_message.delay(case_id, version)
    except OperationalError:
        fail(case_id, version)


def schedule(case):
    transaction.on_commit(partial(_enqueue, str(case.pk), case.version))
