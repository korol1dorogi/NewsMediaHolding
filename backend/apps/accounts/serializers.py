from collections.abc import Mapping

from rest_framework import serializers


class LoginInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"request": ["Ожидается объект."]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({"request": ["Неизвестные поля запроса."]})
        return super().to_internal_value(data)


class UserOutput(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    username = serializers.CharField(read_only=True)
    role = serializers.ChoiceField(
        choices=["user", "lawyer", "moderator", "editor"], read_only=True
    )
    is_demo = serializers.BooleanField(read_only=True)
