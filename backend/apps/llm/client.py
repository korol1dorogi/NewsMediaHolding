"""JSON-only LLM access, isolated from application-specific workflows."""

import json
import logging
import re
import time
from pathlib import Path
from urllib import error, request

from django.conf import settings
from rest_framework import serializers

from .schema import UnsupportedSchema, serializer_schema

logger = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parent
_NAME = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")
_TIMEOUT_SECONDS = 30


class LLMError(Exception):
    """A model response could not be obtained or validated."""


def _name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise LLMError("Invalid task or scenario")
    return value


def _mock_response(task, payload):
    scenario = _name(payload.get("scenario"))
    return (_ROOT / "mock_responses" / task / f"{scenario}.json").read_text(encoding="utf-8")


def _remote_response(task, payload, schema_description):
    base_url = settings.LLM_BASE_URL.rstrip("/")
    api_key = settings.LLM_API_KEY
    model = settings.LLM_MODEL
    if not base_url or not api_key or not model:
        raise LLMError("LLM provider configuration is incomplete")
    if not base_url.startswith(("https://", "http://")):
        raise LLMError("Invalid LLM provider URL")
    instructions = (_ROOT / "prompts" / "system_v1.txt").read_text(encoding="utf-8")
    # Only explicitly registered, versioned prompts can become system instructions.
    task_prompts = {"intake": "intake_v1.txt"}
    if task in task_prompts:
        instructions += "\n" + (_ROOT / "prompts" / task_prompts[task]).read_text(encoding="utf-8")
    instructions += "\nRequired JSON Schema for the response:\n" + json.dumps(schema_description)
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": json.dumps({"task": task, "data": payload}, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(  # noqa: S310 — URL scheme is restricted above
        f"{base_url}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        result = json.load(response)
    return result["choices"][0]["message"]["content"]


def complete_json(task, payload, schema):
    """Return a validated dictionary, or raise LLMError without exposing input data.

    ``schema`` is a DRF Serializer class. Mock fixtures are selected using
    ``payload['scenario']``. Provider and configuration come from Django settings.
    """
    start = time.monotonic()
    outcome = "error"
    task_name = "invalid"
    try:
        task_name = _name(task)
        if (
            not isinstance(payload, dict)
            or not isinstance(schema, type)
            or not issubclass(schema, serializers.Serializer)
        ):
            raise LLMError("Invalid client arguments")
        try:
            schema_description = serializer_schema(schema)
        except UnsupportedSchema:
            raise LLMError("Unsupported serializer schema") from None
        provider = settings.LLM_PROVIDER
        if provider not in {"mock", "openai"}:
            raise LLMError("Unsupported LLM provider")
        for attempt in range(2):
            try:
                raw = (
                    _mock_response(task_name, payload)
                    if provider == "mock"
                    else _remote_response(task_name, payload, schema_description)
                )
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("Response is not an object")
                serializer = schema(data=data)
                serializer.is_valid(raise_exception=True)
                result = dict(serializer.validated_data)
                outcome = "success"
                return result
            except (
                OSError,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
                serializers.ValidationError,
                error.URLError,
            ):
                if attempt == 1:
                    raise LLMError("LLM response unavailable or invalid") from None
        raise LLMError("LLM response unavailable or invalid")
    finally:
        logger.info(
            "LLM task=%s duration=%.3f outcome=%s", task_name, time.monotonic() - start, outcome
        )
