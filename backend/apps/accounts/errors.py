from django.http import JsonResponse
from django.views import defaults
from django.views.csrf import csrf_failure as django_csrf_failure
from rest_framework.views import exception_handler as default_exception_handler


def error_payload(code, message, details=None):
    return {"code": code, "message": message, "details": details or {}}


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse(
            error_payload("permission_denied", "Проверка CSRF не пройдена."), status=403
        )
    return django_csrf_failure(request, reason=reason)


def not_found(request, exception):
    if request.path.startswith("/api/"):
        return JsonResponse(error_payload("not_found", "Объект не найден."), status=404)
    return defaults.page_not_found(request, exception)


def exception_handler(exc, context):
    response = default_exception_handler(exc, context)
    if response is None:
        return response
    code, message = {
        400: ("validation_error", "Некорректные данные."),
        401: ("authentication_required", "Вход не выполнен или учётные данные неверны."),
        403: ("permission_denied", "Доступ запрещён."),
        404: ("not_found", "Объект не найден."),
        405: ("method_not_allowed", "Метод не поддерживается."),
        415: ("unsupported_media_type", "Формат запроса не поддерживается."),
        429: ("throttled", "Слишком много попыток входа. Повторите позже."),
        503: ("auth_unavailable", "Вход временно недоступен."),
    }.get(response.status_code, ("request_error", "Не удалось выполнить запрос."))
    details = {}
    if response.status_code == 400 and isinstance(response.data, dict):
        for key, value in response.data.items():
            details[str(key)] = (
                [str(item) for item in value] if isinstance(value, list) else [str(value)]
            )
    response.data = error_payload(code, message, details)
    return response
