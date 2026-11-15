from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.response import Response

from apps.cases import serializers as case_dto
from apps.cases.states import Conflict, transition
from apps.cases.views import CaseView, check_version, owned, validated
from apps.guidance.drafting import missing_facts

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
        # Wave 2: no payment yet. B6 freezes the claim price here via payments.hold.
        transition(case, "claim_in_review")
        claim.submitted_at = timezone.now()
        claim.submit_consent_version = data["consent"]["text_version"][:64]
        claim.save(update_fields=["submitted_at", "submit_consent_version"])
        case.version += 1
        case.save()
        return Response(case_dto.Detail(case).data)
