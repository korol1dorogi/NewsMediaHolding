"""Synthetic-only adapter for preparing K1 pool drafts.

The input adapter is internal test scaffolding, not a Case or API schema. B9
must connect confirmed snapshots and trusted B3/B11 results once they exist.
This implementation does not send data to a model and does not persist drafts.
"""

from dataclasses import dataclass, field

from django.conf import settings
from rest_framework import serializers

from .pii import KnownPersonalData, scan


class UnsafeOutput(Exception):
    """No safe draft could be produced; B9 must route for moderation."""


class InvalidOutput(Exception):
    """The internal adapter or a mock response is invalid."""


@dataclass(frozen=True, repr=False)
class MockCaseAdapter:
    """Synthetic adapter with no field values in its representation."""

    scenario: str
    category: str
    city: str
    amount_range: dict[str, int]
    company: dict[str, str]
    actions_taken: list[str]
    similar_cases: dict[str, int]
    source_description: str = field(repr=False)
    personal_data: KnownPersonalData = field(repr=False)


class _AmountRangeSerializer(serializers.Serializer):
    min_kopecks = serializers.IntegerField(min_value=0)
    max_kopecks = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        if attrs["min_kopecks"] > attrs["max_kopecks"]:
            raise serializers.ValidationError("Invalid amount range")
        return attrs


class _CompanySerializer(serializers.Serializer):
    name = serializers.CharField(allow_blank=False, trim_whitespace=False)
    status = serializers.ChoiceField(choices=("active", "liquidating", "bankrupt", "unavailable"))


class _SimilarCasesSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    cities_count = serializers.IntegerField(min_value=0)
    period_months = serializers.IntegerField(min_value=1)


class _DraftSerializer(serializers.Serializer):
    category = serializers.CharField(allow_blank=False, trim_whitespace=False)
    description = serializers.CharField(allow_blank=False, trim_whitespace=False)
    city = serializers.CharField(allow_blank=False, trim_whitespace=False)
    amount_range = _AmountRangeSerializer()
    company = _CompanySerializer()
    actions_taken = serializers.ListField(
        child=serializers.CharField(allow_blank=False, trim_whitespace=False)
    )
    similar_cases = _SimilarCasesSerializer()


def _mock_description(scenario: str) -> str:
    """Return only the synthetic Anya scenario, with no source text lookup."""
    if scenario != "anya":
        raise InvalidOutput("Unsupported mock scenario")
    return "Потребитель просит вернуть оплату за вымышленный онлайн-курс."


def _public_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _public_strings(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from _public_strings(child)


def _contains_sensitive(value, personal_data):
    try:
        return bool(scan(value, personal_data))
    except Exception:
        # Scanner exceptions can contain private input; do not expose a cause.
        raise UnsafeOutput("Pool draft requires moderation") from None


def anonymize(case: MockCaseAdapter) -> dict:
    """Return an S3-screened draft or a content-free error; never publish it.

    Only the mock provider and synthetic adapter are supported. Source facts,
    company data and aggregates are supplied by the trusted caller; this
    service cannot assert whether those values were actually confirmed.
    After an unsafe second result B9 must handle UnsafeOutput for moderation.
    """
    if settings.LLM_PROVIDER != "mock" or not isinstance(case, MockCaseAdapter):
        raise InvalidOutput("Only the synthetic mock adapter is supported")
    for _ in range(2):
        try:
            description = _mock_description(case.scenario)
            values = {
                "category": case.category,
                "description": description,
                "city": case.city,
                "amount_range": case.amount_range,
                "company": case.company,
                "actions_taken": case.actions_taken,
                "similar_cases": case.similar_cases,
            }
            serializer = _DraftSerializer(data=values)
            serializer.is_valid(raise_exception=True)
            draft = dict(serializer.validated_data)
            if all(
                not _contains_sensitive(value, case.personal_data)
                for value in _public_strings(draft)
            ):
                return draft
        except serializers.ValidationError:
            raise InvalidOutput("Invalid mock draft") from None
        except (TypeError, ValueError):
            raise UnsafeOutput("Pool draft requires moderation") from None
    raise UnsafeOutput("Pool draft requires moderation")
