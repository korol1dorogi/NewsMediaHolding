from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response

from apps.accounts.permissions import IsLawyer
from apps.audit.models import AccessLog, log_access
from apps.cases import serializers as case_dto
from apps.cases.cards import card_data
from apps.cases.states import Conflict
from apps.cases.views import CaseView, check_version, owned, validated
from apps.claims.serializers import PersonalData, claim_dto
from apps.privacy.models import Consent
from apps.privacy.services import record

from . import services
from .models import WorkAssignment


class ConsentVersionInput(case_dto.Versioned):
    consent = case_dto.Consent()


class AcceptOfferInput(ConsentVersionInput):
    personal_data = PersonalData(required=False, allow_null=True)


class OfferInput(case_dto.Input):
    scope = serializers.CharField(max_length=2_000)
    duration_days = serializers.IntegerField(min_value=1, max_value=365)
    price_kopecks = serializers.IntegerField(min_value=1, max_value=100_000_000_00)
    included = serializers.ListField(child=serializers.CharField(max_length=300), max_length=20)
    excluded = serializers.ListField(child=serializers.CharField(max_length=300), max_length=20)


class AcceptWorkInput(case_dto.Versioned):
    work_version = serializers.IntegerField(min_value=1)


class WorkInput(case_dto.Versioned):
    text = serializers.CharField(max_length=20_000)


class PoolFilters(serializers.Serializer):
    category = serializers.CharField(required=False, max_length=64)
    city = serializers.CharField(required=False, max_length=128)
    min_kopecks = serializers.IntegerField(required=False, min_value=0)
    max_kopecks = serializers.IntegerField(required=False, min_value=0)


# --- owner ---------------------------------------------------------------------------


class Publish(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(ConsentVersionInput, request)
        check_version(case, data)
        if case.state != "in_pool" or case.path != "specialist":
            raise Conflict()
        card, created = services.publish(case)
        if created:
            record(
                request.user,
                Consent.Kind.PUBLISH_POOL,
                data["consent"],
                case=case,
                reference_id=card.pk,
            )
            case.version += 1
            case.save()
        return Response(services.owner_pool_status(card), status=202)


class Offers(CaseView):
    def get(self, request, case_id):
        case = owned(request.user, case_id)
        return Response({"items": [services.offer_dto(o) for o in services.offers_for_owner(case)]})


class AcceptOffer(CaseView):
    @transaction.atomic
    def post(self, request, case_id, offer_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(AcceptOfferInput, request)
        check_version(case, data)
        return Response(
            case_dto.Detail(services.accept_offer(request.user, case, offer_id, data)).data
        )


class AcceptWork(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(AcceptWorkInput, request)
        check_version(case, data)
        return Response(case_dto.Detail(services.accept_work(case, data["work_version"])).data)


# --- lawyer --------------------------------------------------------------------------


class LawyerView(CaseView):
    permission_classes = [IsLawyer]


class Pool(LawyerView):
    def get(self, request):
        filters = PoolFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        cards = services.visible_cards(filters.validated_data)
        return Response({"items": [services.pool_card_dto(card) for card in cards]})


class PoolDetail(LawyerView):
    def get(self, request, card_id):
        return Response(services.pool_card_dto(services.visible_card(card_id)))


class MakeOffer(LawyerView):
    def post(self, request, card_id):
        data = validated(OfferInput, request)
        services.sweep()
        offer = services.make_offer(request.user, card_id, data)
        return Response(services.offer_dto(offer), status=201)


def _lawyer_summary(case):
    data = case_dto.Summary(case).data
    data["available_actions"] = services.lawyer_actions(case)
    return data


class LawyerCases(LawyerView):
    def get(self, request):
        services.sweep()
        assignments = WorkAssignment.objects.filter(
            lawyer=request.user,
            status=WorkAssignment.Status.ACTIVE,
            case__state__in=services.LAWYER_STATES,
        ).select_related("case")
        return Response({"items": [_lawyer_summary(item.case) for item in assignments]})


class LawyerCaseDetail(LawyerView):
    @transaction.atomic
    def get(self, request, case_id):
        assignment = services.lawyer_assignment(request.user, case_id)
        case = assignment.case
        personal = services.personal_data(case)
        log_access(request.user, "case", case.pk, AccessLog.Basis.ACCEPTED_OFFER, case_id=case.pk)
        claim = case.claim if hasattr(case, "claim") and case.claim.ready else None
        return Response(
            {
                "case": _lawyer_summary(case),
                "card": card_data(case),
                "personal_data": {
                    "full_name": personal.full_name,
                    "reply_address": personal.reply_address,
                    "contract_reference": personal.contract_reference,
                },
                "documents": case_dto.DocumentData(
                    case.documents.order_by("created_at", "pk"), many=True
                ).data,
                "claim": claim_dto(case, claim) if claim else None,
                "accepted_offer": services.offer_dto(assignment.offer),
                "work": services.work_dto(services.current_work(case)),
            }
        )


class Start(LawyerView):
    def post(self, request, case_id):
        data = validated(case_dto.Versioned, request)
        return Response(
            _lawyer_summary(services.start(request.user, case_id, data["expected_version"]))
        )


class SubmitWork(LawyerView):
    def post(self, request, case_id):
        data = validated(WorkInput, request)
        case = services.submit_work(request.user, case_id, data["expected_version"], data["text"])
        return Response(_lawyer_summary(case))
