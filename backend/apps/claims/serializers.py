import unicodedata
from datetime import UTC

from rest_framework import serializers

from apps.cases.serializers import Consent, Input, Versioned
from apps.cases.states import available_actions

from .models import personalize


def _clean(value, field):
    value = value.strip()
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise serializers.ValidationError({field: ["Недопустимые символы."]})
    return value


class PersonalData(Input):
    full_name = serializers.CharField(max_length=200)
    reply_address = serializers.CharField(max_length=500)
    contract_reference = serializers.CharField(max_length=200)

    def validate(self, attrs):
        return {key: _clean(value, key) for key, value in attrs.items()}


class PersonalDataInput(Versioned):
    data = PersonalData()
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if value is not True:
            raise serializers.ValidationError("Подтвердите данные.")
        return value


class ClaimVersionInput(Versioned):
    claim_version = serializers.IntegerField(min_value=1)


class SubmitInput(ClaimVersionInput):
    consent = Consent()


def _time(value):
    return (
        serializers.DateTimeField(default_timezone=UTC).to_representation(value) if value else None
    )


def _date(value):
    return value.isoformat() if value else None


def claim_dto(case, claim):
    personal = getattr(claim, "personal_data", None) if hasattr(claim, "personal_data") else None
    return {
        "id": str(claim.pk),
        "case_id": str(case.pk),
        "case_version": case.version,
        "current_version": claim.current_version,
        "versions": [
            {
                "version": item.version,
                "author": item.author,
                "text": personalize(item.template_text, personal),
                "comment": item.comment or None,
                "created_at": _time(item.created_at),
            }
            for item in claim.versions.all()
        ],
        "personal_data": {
            "full_name": personal.full_name,
            "reply_address": personal.reply_address,
            "contract_reference": personal.contract_reference,
        }
        if personal
        else None,
        "personal_data_confirmed": claim.personal_data_confirmed,
        "faulty": claim.faulty,
        "submitted_at": _time(claim.submitted_at),
        "sent_on": _date(claim.sent_on),
        "response_due_on": _date(claim.response_due_on),
        "available_actions": available_actions(case),
    }
