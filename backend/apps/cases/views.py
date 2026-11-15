from io import BytesIO
from pathlib import PurePath

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import serializers as dto
from .models import Case, Document, Message
from .states import INTAKE_STATES, UPLOAD_STATES, Conflict, can_close, transition
from .tasks import schedule


def validated(serializer, request):
    data = serializer(data=request.data)
    data.is_valid(raise_exception=True)
    return data.validated_data


def owned(user, case_id, *, lock=False):
    cases = Case.objects.filter(owner=user)
    if lock:
        cases = cases.select_for_update()
    return get_object_or_404(cases, pk=case_id)


def check_version(case, data):
    if data["expected_version"] != case.version:
        raise Conflict()


class Session(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"


class CaseView(APIView):
    authentication_classes = [Session]

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        errors = {
            400: ("validation_error", "Некорректные данные"),
            401: ("authentication_required", "Необходимо войти"),
            403: ("permission_denied", "Доступ запрещён"),
            404: ("not_found", "Объект не найден"),
            409: ("conflict", "Недопустимый переход или устаревшая версия"),
        }
        if response.status_code in errors:
            code, message = errors[response.status_code]
            response.data = {"code": code, "message": message, "details": {}}
        return response


class Cases(CaseView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request.user, "role", "user") != "user":
            raise PermissionDenied()

    def get(self, request):
        cases = Case.objects.filter(owner=request.user).order_by("-created_at", "pk")
        return Response({"items": dto.Summary(cases, many=True).data})

    @transaction.atomic
    def post(self, request):
        data = validated(dto.Create, request)
        case = Case.objects.create(
            owner=request.user, consent_text_version=data["consent"]["text_version"]
        )
        Message.objects.create(case=case, author="user", text=data["message"])
        schedule(case)
        return Response(dto.Detail(case).data, status=201)


class CaseDetail(CaseView):
    def get(self, request, case_id):
        return Response(dto.Detail(owned(request.user, case_id)).data)


class Messages(CaseView):
    def get(self, request, case_id):
        case = owned(request.user, case_id)
        return Response({"items": dto.MessageData(case.messages.all(), many=True).data})

    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(dto.Send, request)
        check_version(case, data)
        if case.state not in INTAKE_STATES or case.ai_state == "thinking":
            raise Conflict()
        if case.state == "clarifying":
            transition(case, "draft")
        case.ai_state = "thinking"
        case.version += 1
        case.save()
        message = Message.objects.create(case=case, author="user", text=data["text"])
        schedule(case)
        return Response(
            {"case": dto.Summary(case).data, "message": dto.MessageData(message).data}, status=202
        )


class CloseCase(CaseView):
    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(dto.Close, request)
        check_version(case, data)
        if not can_close(case):
            raise Conflict()
        transition(case, "closed")
        case.ai_state = "idle"
        case.close_reason = data["reason"]
        case.version += 1
        case.save()
        return Response(dto.Detail(case).data)


def read_document(upload):
    # Bound the private DB blob using Django's existing in-memory upload threshold.
    if upload.size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
        raise ValidationError("Файл слишком большой.")
    content = upload.read()
    suffix = PurePath(upload.name).suffix.lower()
    if content.startswith(b"\x89PNG\r\n\x1a\n") and suffix == ".png":
        mime = "image/png"
    elif content.startswith(b"\xff\xd8\xff") and suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".txt" and b"\x00" not in content:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError("Нужен текст UTF-8.") from exc
        mime = "text/plain"
    else:
        raise ValidationError("Неподдерживаемый файл.")
    if mime != upload.content_type:
        raise ValidationError("Тип файла не совпадает с содержимым.")
    return mime, content


class Documents(CaseView):
    parser_classes = [MultiPartParser]

    @transaction.atomic
    def post(self, request, case_id):
        case = owned(request.user, case_id, lock=True)
        data = validated(dto.Upload, request)
        check_version(case, data)
        if case.state not in UPLOAD_STATES or case.card_confirmed_at is not None:
            raise Conflict()
        mime, content = read_document(data["file"])
        doc = Document.objects.create(
            case=case,
            filename=data["file"].name,
            content=content,
            content_type=mime,
            size_bytes=len(content),
        )
        case.version += 1
        case.save()
        if case.ai_state == "thinking":
            schedule(case)
        return Response(dto.DocumentData(doc).data, status=201)


class Download(CaseView):
    def perform_content_negotiation(self, request, force=False):
        # The stored document determines the binary response's content type.
        return super().perform_content_negotiation(request, force=True)

    def get(self, request, case_id, document_id):
        doc = get_object_or_404(Document, case__owner=request.user, case_id=case_id, pk=document_id)
        response = FileResponse(
            BytesIO(bytes(doc.content)),
            as_attachment=True,
            filename=doc.filename,
            content_type=doc.content_type,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
