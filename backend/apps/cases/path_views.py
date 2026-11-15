from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response

from apps.companies.services import as_dto, check_case
from apps.guidance.plan import PATH_TARGET_STATE, build_plan, path_options

from . import serializers as dto
from .states import Conflict, transition
from .views import CaseView, check_version, owned, validated


class PathInput(dto.Versioned):
    path = serializers.ChoiceField(choices=list(PATH_TARGET_STATE))


def confirmed(user, case_id, *, lock=False):
    case = owned(user, case_id, lock=lock)
    if case.card_confirmed_at is None:
        raise Conflict()
    return case


class Company(CaseView):
    @transaction.atomic
    def get(self, request, case_id):
        return Response(as_dto(check_case(confirmed(request.user, case_id))))


class Paths(CaseView):
    @transaction.atomic
    def get(self, request, case_id):
        case = confirmed(request.user, case_id)
        return Response({"items": path_options(case, check_case(case).status)})


class ChoosePath(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = confirmed(request.user, case_id, lock=True)
        data = validated(PathInput, request)
        check_version(case, data)
        options = path_options(case, check_case(case).status)
        option = next(item for item in options if item["path"] == data["path"])
        if not option["available"]:
            raise Conflict(fields=["path"])
        transition(case, PATH_TARGET_STATE[data["path"]])
        case.path = data["path"]
        case.version += 1
        case.save()
        return Response(dto.Detail(case).data)


class Plan(CaseView):
    @transaction.atomic
    def get(self, request, case_id):
        case = confirmed(request.user, case_id)
        return Response(build_plan(case, check_case(case).status))
