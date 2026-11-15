"""companies.check(inn) and the per-case snapshot used by paths and plans."""

from datetime import UTC

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cases.facts import COMPANY_INN, COMPANY_NAME, confirmed_values

from .inn import normalize_inn
from .models import CompanyCheck
from .providers import PROVIDERS, ProviderUnavailable


class InvalidInn(ValueError):
    """The INN has a wrong length or checksum; it is never sent to a registry."""


def check(inn):
    """Return CompanyCheck fields. A provider failure is ``unavailable``, never ``active``."""
    normalized = normalize_inn(inn)
    if normalized is None:
        raise InvalidInn("Invalid INN")
    lookup = PROVIDERS.get(settings.COMPANIES_PROVIDER, PROVIDERS["mock"])
    try:
        result = lookup(normalized)
    except ProviderUnavailable:
        result = {
            "status": CompanyCheck.Status.UNAVAILABLE,
            "name": None,
            "registered_on": None,
            "source": settings.COMPANIES_PROVIDER,
            "is_demo": False,
        }
    return {**result, "inn": normalized}


def _unavailable(case, source, name=None):
    return {
        "status": CompanyCheck.Status.UNAVAILABLE,
        "name": name,
        "inn": None,
        "registered_on": None,
        "source": source,
        "is_demo": False,
    }


def check_case(case):
    """One stored check per confirmed card version; repeated reads do not call the registry."""
    existing = case.company_checks.filter(card_version=case.card_snapshot.version).first()
    if existing:
        return existing
    facts = confirmed_values(case)
    raw_inn = facts.get(COMPANY_INN)
    if not raw_inn:
        result = _unavailable(case, "inn_missing", facts.get(COMPANY_NAME))
    else:
        try:
            result = check(raw_inn)
        except InvalidInn:
            result = _unavailable(case, "inn_invalid", facts.get(COMPANY_NAME))
    if result["status"] == CompanyCheck.Status.UNAVAILABLE and not result.get("name"):
        result["name"] = facts.get(COMPANY_NAME)
    try:
        with transaction.atomic():
            return CompanyCheck.objects.create(
                case=case,
                card_version=case.card_snapshot.version,
                status=result["status"],
                name=result.get("name") or "",
                inn=result.get("inn") or "",
                registered_on=result.get("registered_on"),
                source=result["source"],
                is_demo=bool(result.get("is_demo")),
                checked_at=timezone.now(),
            )
    except IntegrityError:
        return case.company_checks.get(card_version=case.card_snapshot.version)


def as_dto(item):
    return {
        "status": item.status,
        "name": item.name or None,
        "inn": item.inn or None,
        "registered_on": item.registered_on.isoformat()
        if hasattr(item.registered_on, "isoformat")
        else item.registered_on,
        "source": item.source,
        "checked_at": item.checked_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_demo": item.is_demo,
    }
