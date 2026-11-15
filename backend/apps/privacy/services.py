"""record(): every consent point stores who agreed to which text version, and when.

The server never accepts on the user's behalf: callers pass the validated ``consent``
block from the request (``accepted`` is checked to be ``true`` by the serializer).
"""

from rest_framework.exceptions import ValidationError

from .models import CONSENT_TEXTS, Consent


def check_version(text_version):
    if text_version not in CONSENT_TEXTS:
        raise ValidationError({"consent": ["Неизвестная версия текста согласия."]})
    return text_version


def record(user, kind, consent, *, case=None, reference_id=None):
    if not isinstance(consent, dict) or consent.get("accepted") is not True:
        raise ValidationError({"consent": ["Необходимо согласие."]})
    return Consent.objects.create(
        user=user,
        kind=kind,
        text_version=check_version(consent.get("text_version")),
        case=case,
        reference_id=reference_id,
    )
