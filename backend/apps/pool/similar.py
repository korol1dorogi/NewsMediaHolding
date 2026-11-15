"""«Вы не один» (B11): confirmed cases about the same company, matched by INN only.

Only aggregates leave this module: a count, the number of cities and the period. Other
people's cases, values and identifiers are never returned.
"""

from django.utils import timezone

from apps.cases.facts import CITY, COMPANY_INN
from apps.cases.models import CardSnapshot
from apps.companies.inn import normalize_inn


def _value(facts, key):
    for row in facts:
        if row.get("key") == key and isinstance(row.get("value"), str):
            return row["value"].strip()
    return None


def similar_cases(case):
    """Aggregates for ``case``, or None when its card is not confirmed or INN is invalid."""
    snapshot = getattr(case, "card_snapshot", None) if case.card_confirmed_at else None
    if snapshot is None:
        return None
    inn = normalize_inn(_value(snapshot.facts, COMPANY_INN))
    if inn is None:
        return None
    others = (
        CardSnapshot.objects.filter(
            facts__contains=[{"key": COMPANY_INN, "value": inn}],
            case__card_confirmed_at__isnull=False,
        )
        .exclude(case_id=case.pk)
        .only("facts", "confirmed_at")
    )
    count = 0
    cities = set()
    earliest = None
    for other in others:
        count += 1
        city = _value(other.facts, CITY)
        if city:
            cities.add(city.casefold())
        if earliest is None or other.confirmed_at < earliest:
            earliest = other.confirmed_at
    months = 1
    if earliest is not None:
        now = timezone.now()
        months = max(1, (now.year - earliest.year) * 12 + now.month - earliest.month + 1)
    return {"count": count, "cities_count": len(cities), "period_months": months}
