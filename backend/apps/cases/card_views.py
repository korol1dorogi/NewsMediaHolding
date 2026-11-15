from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from . import serializers as dto
from .cards import card_data
from .models import CardSnapshot, Fact
from .states import Conflict, transition
from .views import CaseView, check_version, owned, validated


def editable(user, case_id):
    case = owned(user, case_id, lock=True)
    if case.state != "card_ready" or case.card_confirmed_at is not None:
        raise Conflict()
    return case


class Card(CaseView):
    @transaction.atomic
    def get(self, request, case_id):
        return Response(card_data(owned(request.user, case_id, lock=True)))


class EditFact(CaseView):
    @transaction.atomic
    def patch(self, request, case_id, key):
        case = editable(request.user, case_id)
        data = validated(dto.EditFact, request)
        check_version(case, data)
        fact = get_object_or_404(case.facts, key=key)
        fact.value = data["value"]
        fact.status = Fact.Status.USER_EDITED
        fact.source = None
        fact.source_quote = ""
        fact.save()
        case.version += 1
        case.card_version += 1
        case.save()
        return Response(card_data(case))


class Confirm(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = editable(request.user, case_id)
        data = validated(dto.ConfirmCard, request)
        fields = []
        if data["expected_version"] != case.version:
            fields.append("expected_version")
        if data["card_version"] != case.card_version:
            fields.append("card_version")
        card = card_data(case)
        fields = fields or card["missing_required_fields"]
        if not card["facts"] and not fields:
            fields = ["facts"]
        if fields:
            return Response(
                {
                    "code": "conflict",
                    "message": "Проверьте версию и обязательные поля.",
                    "details": {"fields": fields},
                },
                status=409,
            )
        transition(case, "card_confirmed")
        case.card_confirmed_at = timezone.now()
        case.version += 1
        case.save()
        CardSnapshot.objects.create(
            case=case,
            version=case.card_version,
            confirmed_at=case.card_confirmed_at,
            facts=card["facts"],
        )
        return Response(dto.Detail(case).data)
