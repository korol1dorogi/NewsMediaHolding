"""Pool card (B9), offers, choosing a lawyer, work and acceptance (B10).

Order of trust: the card is built from the confirmed snapshot, anonymised (A5 on the mock,
code otherwise), screened by S3, and then waits for a moderator. Personal data is revealed
only to the lawyer whose offer the owner accepted and paid for (demo hold).
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.accounts.models import LawyerProfile
from apps.cases.facts import (
    ACTIONS_TAKEN,
    AMOUNT,
    CITY,
    COMPANY_NAME,
    confirmed_values,
    parse_amount,
)
from apps.cases.models import Case
from apps.cases.states import Conflict, transition
from apps.claims.models import Claim, ExcludedReviewer, ReviewAssignment
from apps.companies.services import check_case
from apps.payments import services as payments
from apps.payments.models import HoldStatus, Purpose

from . import anonymize as a5
from .models import CaseContact, Offer, PoolCard, WorkAssignment, WorkSubmission
from .pii import KnownPersonalData, amount_range, scan

CATEGORY = "prepaid_services"
NO_CITY = "Город не указан"
GENERIC_DESCRIPTION = "Потребитель требует вернуть оплату за предоплаченную услугу."
MAX_OFFERS_SHOWN = 5
RATING_FOR_WORK = 1


def _now():
    return timezone.now()


# --- known personal data -------------------------------------------------------------


def personal_data(case):
    """Owner's confirmed contacts: from the claim, or given when accepting an offer."""
    claim = Claim.objects.filter(case=case).select_related("personal_data").first()
    personal = getattr(claim, "personal_data", None) if claim else None
    if personal is not None and claim.personal_data_confirmed:
        return personal
    return CaseContact.objects.filter(case=case).first()


def _known(case):
    personal = personal_data(case)
    if personal is None:
        return KnownPersonalData()
    return KnownPersonalData(
        names=(personal.full_name,),
        addresses=(personal.reply_address,),
        contract_numbers=(personal.contract_reference,),
    )


def _safe(text, known):
    try:
        return not scan(text, known)
    except ValueError:
        return False


# --- B9: pool card ---------------------------------------------------------------------


def _actions_taken(case, facts):
    claim = Claim.objects.filter(case=case).first()
    result = []
    if claim is not None and claim.sent_on:
        result.append(
            "Претензия отправлена, компания отказала."
            if claim.outcome == "refused"
            else "Претензия отправлена, ответа нет."
        )
    elif facts.get(ACTIONS_TAKEN):
        result.append("Пользователь уже обращался в компанию.")
    return result


def build_draft(case, company):
    """Anonymised draft; ``scanner_flagged`` tells the moderator to look twice."""
    facts = confirmed_values(case)
    known = _known(case)
    amount = parse_amount(facts.get(AMOUNT)) or 0
    city = facts.get(CITY) or NO_CITY
    if city != NO_CITY and not _safe(city, known):
        city = NO_CITY
    values = {
        "category": CATEGORY,
        "city": city,
        "amount_range": amount_range(amount),
        "company": {
            "name": company.name or facts.get(COMPANY_NAME) or "Компания",
            "status": company.status,
        },
        "actions_taken": _actions_taken(case, facts),
    }
    flagged = False
    try:
        if settings.LLM_PROVIDER != "mock":
            raise a5.InvalidOutput("A5 supports only the mock provider")
        draft = a5.anonymize(
            a5.MockCaseAdapter(
                scenario="anya",
                similar_cases={"count": 0, "cities_count": 0, "period_months": 1},
                source_description="",
                personal_data=known,
                **values,
            )
        )
        description = draft["description"]
    except a5.UnsafeOutput:
        description, flagged = GENERIC_DESCRIPTION, True
    except a5.InvalidOutput:
        description = GENERIC_DESCRIPTION
    if not all(_safe(text, known) for text in (description, values["company"]["name"])):
        description, flagged = GENERIC_DESCRIPTION, True
    return {**values, "description": description, "scanner_flagged": flagged}


@transaction.atomic
def publish(case):
    """One card per case; a repeat returns the same record (contract: idempotent)."""
    existing = PoolCard.objects.filter(case=case).first()
    if existing is not None:
        return existing, False
    company = check_case(case)
    draft = build_draft(case, company)
    try:
        with transaction.atomic():
            card = PoolCard.objects.create(
                case=case,
                card_version=case.card_snapshot.version,
                category=draft["category"],
                description=draft["description"],
                city=draft["city"],
                amount_min_kopecks=draft["amount_range"]["min_kopecks"],
                amount_max_kopecks=draft["amount_range"]["max_kopecks"],
                company_name=draft["company"]["name"],
                company_status=draft["company"]["status"],
                company_inn=company.inn,
                actions_taken=draft["actions_taken"],
                scanner_flagged=draft["scanner_flagged"],
            )
    except IntegrityError:
        return PoolCard.objects.get(case=case), False
    return card, True


def approve(card):
    if card.moderation_status == PoolCard.Moderation.APPROVED:
        return card
    card.moderation_status = PoolCard.Moderation.APPROVED
    card.rejection_reason = ""
    card.approved_at = _now()
    card.offers_until = card.approved_at + timedelta(hours=settings.OFFERS_WINDOW_HOURS)
    card.save(
        update_fields=["moderation_status", "rejection_reason", "approved_at", "offers_until"]
    )
    return card


def reject(card, reason):
    card.moderation_status = PoolCard.Moderation.REJECTED
    card.rejection_reason = reason
    card.save(update_fields=["moderation_status", "rejection_reason"])
    return card


def visible_cards(filters):
    sweep()
    cards = PoolCard.objects.filter(
        moderation_status=PoolCard.Moderation.APPROVED,
        offers_until__gt=_now(),
        case__state__in=("in_pool", "has_offers"),
    ).select_related("case__card_snapshot")
    if filters.get("category"):
        cards = cards.filter(category=filters["category"])
    if filters.get("city"):
        cards = cards.filter(city__iexact=filters["city"])
    if filters.get("min_kopecks") is not None:
        cards = cards.filter(amount_max_kopecks__gte=filters["min_kopecks"])
    if filters.get("max_kopecks") is not None:
        cards = cards.filter(amount_min_kopecks__lte=filters["max_kopecks"])
    return cards


def visible_card(card_id):
    card = visible_cards({}).filter(pk=card_id).first()
    if card is None:
        raise Http404
    return card


# --- B10: offers -----------------------------------------------------------------------


def may_offer(lawyer, card):
    """A lawyer who reviewed this case's claim may offer only after a refusal or silence,
    and never if that review was found faulty."""
    claim = Claim.objects.filter(case_id=card.case_id).first()
    if claim is None:
        return True
    if ExcludedReviewer.objects.filter(claim=claim, lawyer=lawyer).exists():
        return False
    reviewed = (
        claim.reviewer_id == lawyer.pk
        or ReviewAssignment.objects.filter(
            claim=claim, lawyer=lawyer, status=ReviewAssignment.Status.DONE
        ).exists()
    )
    if not reviewed:
        return True
    return not claim.faulty and claim.outcome in ("refused", "no_response")


@transaction.atomic
def make_offer(lawyer, card_id, data):
    card = PoolCard.objects.select_for_update().filter(pk=card_id).first()
    if card is None:
        raise Http404
    case = Case.objects.select_for_update().get(pk=card.case_id)
    if (
        card.moderation_status != PoolCard.Moderation.APPROVED
        or card.offers_until is None
        or card.offers_until <= _now()
        or case.state not in ("in_pool", "has_offers")
    ):
        raise Http404
    if not may_offer(lawyer, card):
        raise Conflict(fields=["lawyer"])
    if card.offers.filter(lawyer=lawyer).exists():
        raise Conflict(fields=["offer"])
    offer = Offer.objects.create(card=card, lawyer=lawyer, **data)
    if case.state == "in_pool":
        transition(case, "has_offers")
        case.version += 1
        case.save()
    return offer


def offers_for_owner(case):
    card = PoolCard.objects.filter(case=case).first()
    if card is None:
        return []
    ratings = dict(LawyerProfile.objects.values_list("user_id", "rating"))
    offers = list(card.offers.select_related("lawyer"))
    offers.sort(key=lambda item: (-ratings.get(item.lawyer_id, 0), item.created_at))
    accepted = [item for item in offers if item.accepted]
    return accepted or offers[:MAX_OFFERS_SHOWN]


@transaction.atomic
def accept_offer(owner, case, offer_id, data):
    """Hold the price, record consent, reveal personal data to exactly one lawyer."""
    from apps.privacy.models import Consent
    from apps.privacy.services import record

    card = PoolCard.objects.select_for_update().filter(case=case).first()
    offer = card.offers.select_for_update().filter(pk=offer_id).first() if card else None
    if offer is None:
        raise Http404
    if case.state != "has_offers" or card.offers.filter(accepted=True).exists():
        raise Conflict()
    if offer not in offers_for_owner(case):
        raise Http404
    personal = personal_data(case)
    if personal is None:
        given = data.get("personal_data")
        if not given:
            raise ValidationError({"personal_data": ["Укажите данные для юриста."]})
        CaseContact.objects.update_or_create(case=case, defaults={**given, "confirmed_at": _now()})
    record(
        owner, Consent.Kind.TRANSFER_TO_LAWYER, data["consent"], case=case, reference_id=offer.pk
    )
    hold = payments.hold(
        owner, Purpose.LEGAL_SERVICE, offer.pk, offer.price_kopecks, f"offer-accept-{offer.pk}"
    )
    offer.accepted = True
    offer.save(update_fields=["accepted"])
    WorkAssignment.objects.create(case=case, offer=offer, lawyer=offer.lawyer, hold=hold)
    transition(case, "offer_accepted")
    case.version += 1
    case.save()
    return case


# --- B10: the chosen lawyer's case ----------------------------------------------------

LAWYER_STATES = ("offer_accepted", "in_progress", "work_submitted")


def lawyer_assignment(lawyer, case_id, *, lock=False):
    sweep()
    assignments = WorkAssignment.objects.filter(
        case_id=case_id,
        lawyer=lawyer,
        status=WorkAssignment.Status.ACTIVE,
        case__state__in=LAWYER_STATES,
    ).select_related("case", "offer")
    if lock:
        assignments = assignments.select_for_update(of=("self",))
    assignment = assignments.first()
    if assignment is None:
        raise Http404
    if lock:
        assignment.case = Case.objects.select_for_update().get(pk=case_id)
    return assignment


def lawyer_actions(case):
    return {"offer_accepted": ["start_work"], "in_progress": ["submit_work"]}.get(case.state, [])


@transaction.atomic
def start(lawyer, case_id, expected_version):
    assignment = lawyer_assignment(lawyer, case_id, lock=True)
    case = assignment.case
    if expected_version != case.version:
        raise Conflict(fields=["expected_version"])
    transition(case, "in_progress")
    case.version += 1
    case.save()
    return case


@transaction.atomic
def submit_work(lawyer, case_id, expected_version, text):
    assignment = lawyer_assignment(lawyer, case_id, lock=True)
    case = assignment.case
    if expected_version != case.version:
        raise Conflict(fields=["expected_version"])
    transition(case, "work_submitted")
    last = assignment.submissions.first()
    WorkSubmission.objects.create(
        assignment=assignment,
        version=(last.version if last else 0) + 1,
        text=text.strip(),
        accept_by=_now() + timedelta(days=settings.WORK_ACCEPTANCE_DAYS),
    )
    case.version += 1
    case.save()
    return case


def current_work(case):
    assignment = WorkAssignment.objects.filter(case=case).order_by("-created_at").first()
    return assignment.submissions.first() if assignment else None


def _complete(case, assignment, submission, *, auto):
    transition(case, "completed")
    submission.accepted_at = _now()
    submission.auto_accepted = auto
    submission.save(update_fields=["accepted_at", "auto_accepted"])
    if assignment.hold.status == HoldStatus.HELD:
        payments.release(
            assignment.hold,
            HoldStatus.HELD,
            f"work-release-{assignment.hold_id}",
            recipient=assignment.lawyer,
        )
    profile, _ = LawyerProfile.objects.get_or_create(user=assignment.lawyer)
    profile.rating += RATING_FOR_WORK
    profile.save(update_fields=["rating"])
    assignment.status = WorkAssignment.Status.DONE
    assignment.save(update_fields=["status"])
    case.version += 1
    case.save()


@transaction.atomic
def accept_work(case, work_version):
    assignment = (
        WorkAssignment.objects.select_for_update(of=("self",))
        .filter(case=case, status=WorkAssignment.Status.ACTIVE)
        .first()
    )
    if case.state != "work_submitted" or assignment is None:
        raise Conflict()
    submission = assignment.submissions.first()
    if submission is None or submission.version != work_version:
        raise Conflict(fields=["work_version"])
    _complete(case, assignment, submission, auto=False)
    return case


def sweep():
    """Time-based transitions, applied lazily on reads (no Celery beat in the prototype):
    work not accepted within WORK_ACCEPTANCE_DAYS is accepted automatically; a published
    card without offers when the window closes moves the case to ``no_offers``."""
    now = _now()
    due = WorkSubmission.objects.filter(
        accepted_at__isnull=True,
        accept_by__lte=now,
        assignment__status=WorkAssignment.Status.ACTIVE,
        assignment__case__state="work_submitted",
    ).values_list("assignment__case_id", flat=True)
    for case_id in list(due):
        with transaction.atomic():
            case = Case.objects.select_for_update().get(pk=case_id)
            assignment = WorkAssignment.objects.filter(
                case=case, status=WorkAssignment.Status.ACTIVE
            ).first()
            if case.state != "work_submitted" or assignment is None:
                continue
            submission = assignment.submissions.first()
            if submission and submission.accepted_at is None and submission.accept_by <= now:
                _complete(case, assignment, submission, auto=True)
    expired = PoolCard.objects.filter(
        moderation_status=PoolCard.Moderation.APPROVED,
        offers_until__lte=now,
        case__state="in_pool",
    ).values_list("case_id", flat=True)
    for case_id in list(expired):
        with transaction.atomic():
            case = Case.objects.select_for_update().get(pk=case_id)
            if case.state == "in_pool":
                transition(case, "no_offers")
                case.version += 1
                case.save()


# --- DTOs ------------------------------------------------------------------------------


def _time(value):
    return serializers.DateTimeField().to_representation(value) if value else None


def pool_card_dto(card):
    from .similar import similar_cases

    return {
        "id": str(card.pk),
        "category": card.category,
        "description": card.description,
        "city": card.city,
        "amount_range": {
            "min_kopecks": card.amount_min_kopecks,
            "max_kopecks": card.amount_max_kopecks,
        },
        "company": {"name": card.company_name, "status": card.company_status},
        "actions_taken": list(card.actions_taken),
        "similar_cases": similar_cases(card.case)
        or {"count": 0, "cities_count": 0, "period_months": 1},
    }


def offer_dto(offer):
    name = offer.lawyer.get_full_name() or offer.lawyer.username
    return {
        "id": str(offer.pk),
        "lawyer_label": f"Юрист {name}",
        "scope": offer.scope,
        "duration_days": offer.duration_days,
        "price_kopecks": offer.price_kopecks,
        "included": list(offer.included),
        "excluded": list(offer.excluded),
        "accepted": offer.accepted,
        "created_at": _time(offer.created_at),
    }


def work_dto(submission):
    if submission is None:
        return None
    return {
        "version": submission.version,
        "text": submission.text,
        "submitted_at": _time(submission.submitted_at),
    }


def owner_pool_status(card):
    if card is None:
        return None
    return {
        "id": str(card.pk),
        "moderation_status": card.moderation_status,
        "rejection_reason": card.rejection_reason or None,
    }
