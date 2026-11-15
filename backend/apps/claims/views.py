from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.cases import serializers as case_dto
from apps.cases.states import Conflict, transition
from apps.cases.views import CaseView, check_version, owned, validated
from apps.guidance.drafting import missing_facts
from apps.guidance.plan import response_deadline
from apps.payments import services as payments
from apps.payments.models import Purpose
from apps.privacy.models import Consent
from apps.privacy.services import record

from . import review
from . import serializers as dto
from .models import Claim, ClaimPersonalData
from .tasks import schedule


def get_claim(case, *, lock=False, ready=True):
    claims = Claim.objects.filter(case=case)
    if lock:
        claims = claims.select_for_update()
    claim = claims.first()
    if claim is None:
        raise Http404
    if ready and (not claim.ready or case.ai_state == "thinking"):
        raise Conflict()
    return claim


class ClaimView(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(case_dto.Versioned, request)
        check_version(case, data)
        if case.state != "claim_draft" or case.card_confirmed_at is None:
            raise Conflict()
        if case.ai_state == "thinking":
            raise Conflict()
        claim = Claim.objects.select_for_update().filter(case=case).first()
        if claim is not None and claim.ready:
            raise Conflict()
        missing = missing_facts(case)
        if missing:
            raise Conflict(fields=missing)
        if claim is None:
            claim = Claim.objects.create(case=case, card_version=case.card_snapshot.version)
        case.ai_state = "thinking"
        case.version += 1
        case.save()
        schedule(case)
        return Response(
            {"claim_id": str(claim.pk), "case": case_dto.Summary(case).data}, status=202
        )

    def get(self, request, case_id):
        case = owned(request.user, case_id)
        return Response(dto.claim_dto(case, get_claim(case)))


class PersonalDataView(CaseView):
    @transaction.atomic
    def put(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(dto.PersonalDataInput, request)
        check_version(case, data)
        if case.state != "claim_draft":
            raise Conflict()
        claim = get_claim(case, lock=True)
        ClaimPersonalData.objects.update_or_create(
            claim=claim, defaults={**data["data"], "confirmed_at": timezone.now()}
        )
        claim.personal_data_confirmed = True
        claim.save(update_fields=["personal_data_confirmed"])
        case.version += 1
        case.save()
        claim.refresh_from_db()
        return Response(dto.claim_dto(case, claim))


class SubmitView(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(dto.SubmitInput, request)
        check_version(case, data)
        if case.state != "claim_draft":
            raise Conflict()
        claim = get_claim(case, lock=True)
        if not claim.personal_data_confirmed:
            raise Conflict(fields=["personal_data"])
        if data["claim_version"] != claim.current_version:
            raise Conflict(fields=["claim_version"])
        consent = record(
            request.user,
            Consent.Kind.TRANSFER_TO_REVIEWER,
            data["consent"],
            case=case,
            reference_id=claim.pk,
        )
        # Demo escrow: the claim price is frozen until a lawyer approves the claim (B8).
        claim.hold = payments.hold(
            request.user,
            Purpose.CLAIM_REVIEW,
            claim.pk,
            settings.PAYMENTS_CLAIM_PRICE_KOPECKS,
            f"claim-submit-{claim.pk}",
        )
        transition(case, "claim_in_review")
        claim.submitted_at = claim.queued_at = timezone.now()
        claim.submit_consent_version = consent.text_version
        claim.save(update_fields=["hold", "submitted_at", "queued_at", "submit_consent_version"])
        case.version += 1
        case.save()
        return Response(case_dto.Detail(case).data)


class OwnerClaimCommand(CaseView):
    """Owner commands after review: same locking and version rules for each."""

    input_class = dto.ClaimVersionInput
    from_state = ""

    def apply(self, request, case, claim, data):
        raise NotImplementedError

    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(self.input_class, request)
        check_version(case, data)
        if case.state != self.from_state:
            raise Conflict()
        claim = get_claim(case, lock=True)
        if "claim_version" in data and data["claim_version"] != claim.current_version:
            raise Conflict(fields=["claim_version"])
        self.apply(request, case, claim, data)
        case.version += 1
        case.save()
        return Response(case_dto.Detail(case).data)


class AcceptEdits(OwnerClaimCommand):
    from_state = "claim_edited"

    def apply(self, request, case, claim, data):
        transition(case, "claim_approved")
        review.pay_reviewer(claim)


class RejectEdits(OwnerClaimCommand):
    input_class = dto.RejectEditsInput
    from_state = "claim_edited"

    def apply(self, request, case, claim, data):
        transition(case, "claim_in_review")
        claim.rejection_comment = data["comment"].strip()
        claim.queued_at = timezone.now()
        claim.reviewer = None
        claim.save(update_fields=["rejection_comment", "queued_at", "reviewer"])


class MarkSent(OwnerClaimCommand):
    input_class = dto.MarkSentInput
    from_state = "claim_approved"

    def apply(self, request, case, claim, data):
        sent_on = data["sent_on"]
        if sent_on > timezone.localdate() or sent_on < timezone.localdate(claim.submitted_at):
            raise ValidationError({"sent_on": ["Дата отправки вне допустимого диапазона."]})
        transition(case, "awaiting_response")
        claim.sent_on = sent_on
        claim.response_due_on = response_deadline(case, presented_on=sent_on).due_on
        claim.save(update_fields=["sent_on", "response_due_on"])


class Outcome(OwnerClaimCommand):
    input_class = dto.OutcomeInput
    from_state = "awaiting_response"

    def apply(self, request, case, claim, data):
        transition(case, "resolved" if data["outcome"] == "resolved" else "no_response")
        claim.outcome = data["outcome"]
        claim.outcome_comment = data["comment"].strip()
        claim.save(update_fields=["outcome", "outcome_comment"])
