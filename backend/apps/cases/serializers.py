from collections.abc import Mapping
from datetime import UTC

from rest_framework import serializers

from .models import Case, Document, Message
from .states import available_actions


class Input(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - self.fields.keys():
            raise serializers.ValidationError({"non_field_errors": ["Неизвестное поле."]})
        return super().to_internal_value(data)


class Consent(Input):
    accepted = serializers.BooleanField()
    text_version = serializers.CharField()

    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or data.get("accepted") is not True:
            raise serializers.ValidationError("Необходимо согласие.")
        return super().to_internal_value(data)


class Create(Input):
    message = serializers.CharField()
    consent = Consent()


class Versioned(Input):
    expected_version = serializers.IntegerField(min_value=1)


class Send(Versioned):
    text = serializers.CharField()


class Close(Versioned):
    reason = serializers.CharField()


class Upload(Versioned):
    file = serializers.FileField(max_length=255)


class Summary(serializers.ModelSerializer):
    available_actions = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(default_timezone=UTC, read_only=True)
    updated_at = serializers.DateTimeField(default_timezone=UTC, read_only=True)

    class Meta:
        model = Case
        fields = (
            "id",
            "state",
            "path",
            "ai_state",
            "version",
            "created_at",
            "updated_at",
            "available_actions",
        )
        read_only_fields = fields

    def get_available_actions(self, case):
        return available_actions(case)


class Detail(Summary):
    pool = serializers.ReadOnlyField(default=None)
    work = serializers.ReadOnlyField(default=None)

    class Meta(Summary.Meta):
        fields = (*Summary.Meta.fields, "card_confirmed_at", "pool", "work")
        read_only_fields = fields


class MessageData(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(default_timezone=UTC, read_only=True)

    class Meta:
        model = Message
        fields = ("id", "author", "text", "created_at")
        read_only_fields = fields


class DocumentData(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(default_timezone=UTC, read_only=True)

    class Meta:
        model = Document
        fields = ("id", "filename", "content_type", "size_bytes", "created_at")
        read_only_fields = fields
