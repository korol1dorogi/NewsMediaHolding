import re
import unicodedata
from io import BytesIO
from pathlib import PurePath

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.privacy.models import Consent
from apps.privacy.services import record

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
            details = {}
            data = response.data
            if isinstance(data, dict) and {"code", "message", "details"} <= data.keys():
                # Already shaped by the global handler (apps.accounts.errors).
                data = data["details"] if isinstance(data["details"], dict) else {}
            if response.status_code == 400 and isinstance(data, dict):
                for key, value in data.items():
                    items = value if isinstance(value, list) else [value]
                    details[str(key)] = [str(item) for item in items]
            elif response.status_code == 409:
                details = getattr(exc, "details", None) or {}
            response.data = {"code": code, "message": message, "details": details}
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
        record(request.user, Consent.Kind.PROCESSING_OFFER, data["consent"], case=case)
        Message.objects.create(case=case, author="user", text=data["message"])
        schedule(case)
        return Response(dto.Detail(case).data, status=201)


class CaseDetail(CaseView):
    def get(self, request, case_id):
        from apps.pool.services import sweep

        sweep()  # time-based transitions: offer window, work auto-acceptance
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


_UNSAFE_NAME = re.compile(r"[^\w .()-]+")
_PDF_ACTIVE = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA|RichMedia|XFA)(?![A-Za-z])"
)


def safe_filename(name, mime):
    """Display name only: files live in the private DB blob under a random UUID."""
    stem = PurePath(str(name).replace("\\", "/")).name
    stem = "".join(ch for ch in stem if not unicodedata.category(ch).startswith("C"))
    stem = _UNSAFE_NAME.sub("_", stem).strip(" .")[:100]
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "text/plain": ".txt",
        "application/pdf": ".pdf",
    }[mime]
    if not stem.lower().endswith((extension, ".jpeg")):
        stem = (stem or "document") + extension
    return stem


def read_document(upload):
    # Bound the private DB blob before reading it into memory.
    if upload.size > settings.DOCUMENTS_MAX_BYTES:
        raise ValidationError({"file": ["Файл слишком большой."]})
    content = upload.read(settings.DOCUMENTS_MAX_BYTES + 1)
    if len(content) > settings.DOCUMENTS_MAX_BYTES:
        raise ValidationError({"file": ["Файл слишком большой."]})
    if not content:
        raise ValidationError({"file": ["Файл пустой."]})
    suffix = PurePath(upload.name).suffix.lower()
    if content.startswith(b"\x89PNG\r\n\x1a\n") and suffix == ".png":
        mime = "image/png"
    elif content.startswith(b"\xff\xd8\xff") and suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif content.startswith(b"%PDF-") and suffix == ".pdf":
        # A7: keep PDFs inert. Active content is refused instead of being sanitised.
        if _PDF_ACTIVE.search(content):
            raise ValidationError({"file": ["PDF с активным содержимым не принимается."]})
        mime = "application/pdf"
    elif suffix == ".txt" and b"\x00" not in content:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": ["Нужен текст UTF-8."]}) from exc
        mime = "text/plain"
    else:
        raise ValidationError({"file": ["Неподдерживаемый файл."]})
    if mime != upload.content_type:
        raise ValidationError({"file": ["Тип файла не совпадает с содержимым."]})
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
        if case.documents.count() >= settings.DOCUMENTS_MAX_PER_CASE:
            raise ValidationError({"file": ["Достигнут лимит файлов в обращении."]})
        mime, content = read_document(data["file"])
        doc = Document.objects.create(
            case=case,
            filename=safe_filename(data["file"].name, mime),
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
        # Owner, or the lawyer whose offer the owner accepted (B10). Reviewers get no originals.
        allowed = Q(case__owner=request.user) | Q(
            case__work_assignments__lawyer=request.user,
            case__work_assignments__status="active",
            case__state__in=("offer_accepted", "in_progress", "work_submitted"),
        )
        doc = get_object_or_404(
            Document.objects.filter(allowed).distinct(), case_id=case_id, pk=document_id
        )
        response = FileResponse(
            BytesIO(bytes(doc.content)),
            as_attachment=True,
            filename=doc.filename,
            content_type=doc.content_type,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        # Never render a stored file as a page, even if a browser ignores the attachment.
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        return response
