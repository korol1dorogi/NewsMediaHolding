from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response

from apps.accounts.permissions import IsLawyer
from apps.audit.models import AccessLog, log_access
from apps.cases import serializers as case_dto
from apps.cases.views import CaseView, validated

from . import review


class TakeInput(case_dto.Versioned):
    pass


class ActionInput(case_dto.Versioned):
    assignment_version = serializers.IntegerField(min_value=1)
    claim_version = serializers.IntegerField(min_value=1)


class EditInput(ActionInput):
    template_text = serializers.CharField(max_length=20_000, trim_whitespace=False)
    comment = serializers.CharField(max_length=2_000)


class LawyerView(CaseView):
    permission_classes = [IsLawyer]


class Queue(LawyerView):
    def get(self, request):
        return Response({"items": review.queue_for(request.user)})


class Take(LawyerView):
    @transaction.atomic
    def post(self, request, claim_id):
        data = validated(TakeInput, request)
        claim, case, assignment = review.take(request.user, claim_id, data["expected_version"])
        return Response(review.review_dto(claim, case, assignment))


class ReviewDetail(LawyerView):
    @transaction.atomic
    def get(self, request, claim_id):
        claim, case, assignment = review.current(request.user, claim_id)
        log_access(
            request.user, "claim", claim.pk, AccessLog.Basis.REVIEW_ASSIGNMENT, case_id=case.pk
        )
        return Response(review.review_dto(claim, case, assignment))


class Approve(LawyerView):
    def post(self, request, claim_id):
        data = validated(ActionInput, request)
        return Response(case_dto.Summary(review.approve(request.user, claim_id, data)).data)


class Edit(LawyerView):
    def post(self, request, claim_id):
        data = validated(EditInput, request)
        return Response(case_dto.Summary(review.edit(request.user, claim_id, data)).data)
