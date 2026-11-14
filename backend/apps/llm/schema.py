"""Translate supported DRF input serializers to JSON Schema for the model."""

from decimal import Decimal

from rest_framework import serializers


class UnsupportedSchema(ValueError):
    """The serializer cannot be represented by the supported JSON Schema subset."""


def _bound(value):
    return float(value) if isinstance(value, Decimal) else value


def _object_schema(serializer):
    properties = {}
    required = []
    for name, field in serializer.fields.items():
        if field.read_only:
            continue
        properties[name] = _field_schema(field)
        if field.required:
            required.append(name)
    result = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        result["required"] = required
    return result


def _field_schema(field):
    if isinstance(field, serializers.ListSerializer):
        result = {"type": "array", "items": _field_schema(field.child)}
        if field.min_length is not None:
            result["minItems"] = field.min_length
        if field.max_length is not None:
            result["maxItems"] = field.max_length
    elif isinstance(field, serializers.Serializer):
        result = _object_schema(field)
    elif type(field) is serializers.ListField:
        result = {"type": "array", "items": _field_schema(field.child)}
        if field.min_length is not None:
            result["minItems"] = field.min_length
        if field.max_length is not None:
            result["maxItems"] = field.max_length
    elif type(field) is serializers.DictField:
        result = {"type": "object", "additionalProperties": _field_schema(field.child)}
    elif type(field) is serializers.ChoiceField:
        choices = list(field.choices)
        if not all(
            isinstance(value, (str, int, float, bool)) or value is None for value in choices
        ):
            raise UnsupportedSchema("Unsupported choice value")
        result = {"enum": choices}
    else:
        types = {
            serializers.CharField: ("string", None),
            serializers.EmailField: ("string", "email"),
            serializers.URLField: ("string", "uri"),
            serializers.UUIDField: ("string", "uuid"),
            serializers.DateField: ("string", "date"),
            serializers.DateTimeField: ("string", "date-time"),
            serializers.TimeField: ("string", "time"),
            serializers.IntegerField: ("integer", None),
            serializers.FloatField: ("number", None),
            serializers.DecimalField: ("number", None),
            serializers.BooleanField: ("boolean", None),
        }
        if type(field) not in types:
            raise UnsupportedSchema("Unsupported serializer field")
        field_type, field_format = types[type(field)]
        result = {"type": field_type}
        if field_format:
            result["format"] = field_format
        for attr, key in (
            ("min_length", "minLength"),
            ("max_length", "maxLength"),
            ("min_value", "minimum"),
            ("max_value", "maximum"),
        ):
            value = getattr(field, attr, None)
            if value is not None:
                result[key] = _bound(value)
        if isinstance(field, serializers.CharField) and not field.allow_blank:
            result["minLength"] = max(1, result.get("minLength", 0))
    if field.allow_null:
        return {"anyOf": [result, {"type": "null"}]}
    return result


def serializer_schema(serializer_class):
    """Return a JSON Schema for the serializer's supported writable fields."""
    return _object_schema(serializer_class())
