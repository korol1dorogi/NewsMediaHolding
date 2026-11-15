"""Review queue and lawyer actions (B6), payout and the faulty-claim rule (B7).

The reviewer never receives the owner's DTOs: ``review_dto`` builds a separate view with
placeholders instead of contacts, scanner-masked facts and no original documents.
"""

import unicodedata
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import LawyerProfile
from apps.audit.models import AccessLog, log_access
from apps.cases.facts import AMOUNT, confirmed_values, parse_amount
from apps.cases.models import Case
from apps.cases.states import Conflict, transition
from apps.payments import services as payments
from apps.payments.models import HoldStatus
from apps.pool.pii import KnownPersonalData, scan

from .models import Claim, ClaimVersion, ExcludedReviewer, ReviewAssignment

CATEGORY = "prepaid_services"
MASK = "[скрыто]"
RATING_FOR_REVIEW = 1
RATING_PENALTY_FAULTY = 5


def _now():
    return timezone.now()


def expire_stale():
    ReviewAssignment.objects.filter(
        status=ReviewAssignment.Status.ACTIVE, expires_at__lte=_now()
    ).update(status=ReviewAssignment.Status.EXPIRED)


def _in_queue(claim):
    """Paid (money held) or a free re-review after a faulty claim."""
    if claim.case.state != "claim_in_review" or claim.submitted_at is None:
        return False
    return claim.faulty or (claim.hold_id is not None and claim.hold.status == HoldStatus.HELD)


def queue_for(lawyer):
    expire_stale()
    claims = (
        Claim.objects.filter(case__state="claim_in_review", submitted_at__isnull=False)
        .exclude(assignments__status=ReviewAssignment.Status.ACTIVE)
        .exclude(excluded__lawyer=lawyer)
        .select_related("case__card_snapshot", "hold")
        .order_by("queued_at", "pk")
    )
    return [
        {
            "id": str(claim.pk),
            "category": CATEGORY,
            "amount_kopecks": parse_amount(confirmed_values(claim.case).get(AMOUNT)) or 0,
            "queued_at": serializers.DateTimeField().to_representation(claim.queued_at),
            "case_version": claim.case.version,
        }
        for claim in claims
        if _in_queue(claim)
    ]


def _locked(claim_id):
    claim = Claim.objects.select_for_update().filter(pk=claim_id).first()
    if claim is None:
        raise Http404
    case = Case.objects.select_for_update().get(pk=claim.case_id)
    claim.case = case
    return claim, case


def take(lawyer, claim_id, expected_version):
    claim, case = _locked(claim_id)
    if not _in_queue(claim) or claim.excluded.filter(lawyer=lawyer).exists():
        raise Http404
    if expected_version != case.version:
        raise Conflict(fields=["expected_version"])
    expire_stale()
    if claim.assignments.filter(status=ReviewAssignment.Status.ACTIVE).exists():
        raise Conflict()
    last = claim.assignments.aggregate(last=Max("version"))["last"] or 0
    assignment = ReviewAssignment.objects.create(
        claim=claim,
        lawyer=lawyer,
        version=last + 1,
        expires_at=_now() + timedelta(hours=settings.CLAIM_REVIEW_TIMEOUT_HOURS),
    )
    log_access(lawyer, "claim", claim.pk, AccessLog.Basis.REVIEW_ASSIGNMENT, case_id=case.pk)
    return claim, case, assignment


def current(lawyer, claim_id, *, lock=False):
    """The lawyer's own unexpired assignment, otherwise 404 (no hint that it exists)."""
    if lock:
        claim, case = _locked(claim_id)
    else:
        claim = Claim.objects.select_related("case").filter(pk=claim_id).first()
        if claim is None:
            raise Http404
        case = claim.case
    assignment = claim.assignments.filter(
        status=ReviewAssignment.Status.ACTIVE, lawyer=lawyer, expires_at__gt=_now()
    ).first()
    if assignment is None or case.state != "claim_in_review":
        raise Http404
    return claim, case, assignment


def _known(claim):
    personal = getattr(claim, "personal_data", None)
    if personal is None:
        return KnownPersonalData()
    return KnownPersonalData(
        names=(personal.full_name,),
        addresses=(personal.reply_address,),
        contract_numbers=(personal.contract_reference,),
    )


def mask(text, known):
    """Hide everything the S3 scanner flags except dates, which the reviewer needs."""
    findings = sorted(
        (item for item in scan(text, known) if item.kind != "date"),
        key=lambda item: item.start,
        reverse=True,
    )
    for item in findings:
        text = text[: item.start] + MASK + text[item.end :]
    return text


def review_dto(claim, case, assignment):
    known = _known(claim)
    version = claim.versions.get(version=claim.current_version)
    facts = []
    for row in case.card_snapshot.facts:
        value = row.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        quote = row.get("source_quote") or value
        facts.append(
            {
                "key": row["key"],
                "display_value": mask(value, known),
                "safe_source_quote": mask(quote, known),
            }
        )
    labels = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "text/plain": "текст",
        "application/pdf": "PDF",
    }
    documents = [
        {
            "id": str(doc.pk),
            "label": f"Документ {index} ({labels.get(doc.content_type, 'файл')})",
            "content_type": doc.content_type,
            # No verified redaction exists yet: originals stay closed to the reviewer.
            "safe_redaction_available": False,
        }
        for index, doc in enumerate(case.documents.order_by("created_at", "pk"), start=1)
    ]
    return {
        "id": str(claim.pk),
        "case_id": str(case.pk),
        "case_version": case.version,
        "assignment_version": assignment.version,
        "assignment_expires_at": serializers.DateTimeField().to_representation(
            assignment.expires_at
        ),
        "version": {
            "version": version.version,
            "template_text": mask(version.template_text, known),
            "comment": version.comment or None,
        },
        "facts": facts,
        "documents": documents,
        "available_actions": ["approve_claim", "edit_claim"],
    }


def _check_versions(claim, case, assignment, data):
    fields = []
    if data["expected_version"] != case.version:
        fields.append("expected_version")
    if data["assignment_version"] != assignment.version:
        fields.append("assignment_version")
    if data["claim_version"] != claim.current_version:
        fields.append("claim_version")
    if fields:
        raise Conflict(fields=fields)


def _rating(lawyer, delta):
    profile, _ = LawyerProfile.objects.get_or_create(user=lawyer)
    profile.rating = max(0, profile.rating + delta)
    profile.save(update_fields=["rating"])


def pay_reviewer(claim):
    """Release the frozen claim price: reviewer's share and the platform's rest (B8)."""
    if claim.hold_id is None or claim.hold.status != HoldStatus.HELD:
        return  # free re-review after a faulty claim: the price was already settled
    payments.release(
        claim.hold, HoldStatus.HELD, f"claim-release-{claim.hold_id}", recipient=claim.reviewer
    )
    _rating(claim.reviewer, RATING_FOR_REVIEW)


@transaction.atomic
def approve(lawyer, claim_id, data):
    claim, case, assignment = current(lawyer, claim_id, lock=True)
    _check_versions(claim, case, assignment, data)
    transition(case, "claim_approved")
    assignment.status = ReviewAssignment.Status.DONE
    assignment.save(update_fields=["status"])
    claim.reviewer = lawyer
    claim.save(update_fields=["reviewer"])
    pay_reviewer(claim)
    case.version += 1
    case.save()
    return case


def clean_template(text):
    if any(unicodedata.category(ch).startswith("C") and ch not in "\n\t" for ch in text):
        raise serializers.ValidationError({"template_text": ["Недопустимые символы."]})
    return text.strip()


@transaction.atomic
def edit(lawyer, claim_id, data):
    claim, case, assignment = current(lawyer, claim_id, lock=True)
    _check_versions(claim, case, assignment, data)
    ClaimVersion.objects.create(
        claim=claim,
        version=claim.current_version + 1,
        author=ClaimVersion.Author.LAWYER,
        author_user=lawyer,
        template_text=clean_template(data["template_text"]),
        comment=data["comment"].strip(),
    )
    transition(case, "claim_edited")
    assignment.status = ReviewAssignment.Status.DONE
    assignment.save(update_fields=["status"])
    claim.current_version += 1
    claim.reviewer = lawyer
    claim.save(update_fields=["current_version", "reviewer"])
    case.version += 1
    case.save()
    return case


@transaction.atomic
def mark_faulty(claim_id):
    """Moderator decision: free re-review by another lawyer, the first one is penalised."""
    claim, case = _locked(claim_id)
    if case.state != "claim_approved" or claim.reviewer_id is None:
        raise Conflict()
    ExcludedReviewer.objects.get_or_create(claim=claim, lawyer=claim.reviewer)
    _rating(claim.reviewer, -RATING_PENALTY_FAULTY)
    transition(case, "claim_in_review")
    claim.faulty = True
    claim.commission_revoked = True
    claim.reviewer = None
    claim.queued_at = _now()
    claim.save(update_fields=["faulty", "commission_revoked", "reviewer", "queued_at"])
    case.version += 1
    case.save()
    return claim
