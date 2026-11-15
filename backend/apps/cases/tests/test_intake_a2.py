from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.cases.intake import EMERGENCY_REPLY, FIELDS, next_step
from apps.cases.models import Case, Document, Message
from apps.cases.tasks import process_message
from apps.llm import LLMError

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(django_user_model):
    owner = django_user_model.objects.create_user(username="intake-test")
    return Case.objects.create(owner=owner, consent_text_version="demo")


def message(case, text):
    return Message.objects.create(case=case, author="user", text=text)


@override_settings(LLM_PROVIDER="mock")
def test_demo_three_turns_requires_verifiable_facts(case):
    message(case, "Учебный проект Демо, 68000 рублей, деньги не возвращают")
    first = next_step(case)
    assert not first["card_ready"] and len(first["questions"]) == 5
    message(case, "1 октября оплатила банковской картой")
    second = next_step(case)
    assert not second["card_ready"] and len(second["questions"]) == 3
    message(case, "ИНН 0000000000, обещали записанные уроки, написала претензию")
    final = next_step(case)
    assert final["card_ready"] and final["questions"] == []
    assert set(f["key"] for f in final["proposed_facts"]) == set(FIELDS)
    assert all(f["status"] == "found" for f in final["proposed_facts"])


@override_settings(LLM_PROVIDER="mock")
@pytest.mark.parametrize(
    ("value", "quote", "index"),
    [("чужой", "выдумка", 0), ("выдумано", "Учебный проект Демо", 0), ("Демо", "Демо", 1)],
)
def test_rejects_invented_quote_value_or_foreign_source(case, monkeypatch, value, quote, index):
    message(case, "Учебный проект Демо")
    mock = Mock(
        return_value={
            "facts": [
                {"key": "company_name", "value": value, "quote": quote, "source_index": index}
            ],
            "urgent": False,
            "category": None,
        }
    )
    monkeypatch.setattr("apps.cases.intake.complete_json", mock)
    fact = next_step(case)["proposed_facts"][0]
    assert fact["status"] == "not_found" and fact["source"] is None and fact["value"] is None


@override_settings(LLM_PROVIDER="mock")
def test_urgent_messages_do_not_call_model_even_on_later_turns(case, monkeypatch):
    message(case, "Мне угрожают")
    message(case, "Теперь о документах")
    mock = Mock(side_effect=AssertionError("model must not run"))
    monkeypatch.setattr("apps.cases.intake.complete_json", mock)
    result = next_step(case)
    assert (
        result["urgent"]
        and result["card_ready"] is False
        and result["questions"] == [EMERGENCY_REPLY]
    )
    mock.assert_not_called()


@override_settings(LLM_PROVIDER="mock")
@pytest.mark.parametrize(
    "text",
    [
        "Мошенники прямо сейчас списывают деньги",
        "Сейчас со счёта списывают деньги",
        "Мне поступают угрозы",
    ],
)
def test_current_danger_patterns_fail_closed(case, text):
    message(case, text)
    assert next_step(case)["urgent"]


@override_settings(LLM_PROVIDER="mock")
def test_image_requests_text_without_reading_image_content(case):
    message(case, "Учебный проект Демо")
    Document.objects.create(
        case=case, filename="mock.png", content_type="image/png", size_bytes=3, content=b"bad"
    )
    result = next_step(case)
    assert any("текстом" in item for item in result["missing_documents"])


@override_settings(LLM_PROVIDER="mock")
def test_emergency_stops_writes_for_owner_and_keeps_foreign_404(case, django_user_model):
    case.ai_state = "thinking"
    case.save()
    message(case, "Мне угрожают")
    process_message.run(str(case.pk), case.version)
    case.refresh_from_db()
    assert case.state == "emergency" and case.ai_state == "idle"
    client = APIClient()
    client.force_login(case.owner)
    url = f"/api/cases/{case.pk}"
    assert client.get(url).data["available_actions"] == ["close_case"]
    assert (
        client.post(
            url + "/messages", {"expected_version": case.version, "text": "ещё"}, format="json"
        ).status_code
        == 409
    )
    upload = SimpleUploadedFile("demo.txt", b"demo", content_type="text/plain")
    assert (
        client.post(
            url + "/documents",
            {"expected_version": case.version, "file": upload},
            format="multipart",
        ).status_code
        == 409
    )
    assert (
        client.patch(
            url + "/card/facts/company_name",
            {"expected_version": case.version, "value": "x"},
            format="json",
        ).status_code
        == 409
    )
    assert (
        client.post(
            url + "/card/confirm",
            {"expected_version": case.version, "card_version": case.card_version},
            format="json",
        ).status_code
        == 409
    )
    client.force_login(django_user_model.objects.create_user(username="foreign"))
    assert client.post(url + "/messages", {}, format="json").status_code == 404
    assert client.post(url + "/close", {}, format="json").status_code == 404
    client.force_login(case.owner)
    assert (
        client.post(
            url + "/close", {"expected_version": case.version, "reason": "Завершено"}, format="json"
        ).status_code
        == 200
    )


@override_settings(LLM_PROVIDER="mock")
def test_model_detected_emergency_overrides_facts_and_questions(case, monkeypatch):
    message(case, "Неочевидное описание опасной ситуации")
    monkeypatch.setattr(
        "apps.cases.intake.complete_json",
        Mock(return_value={"facts": [], "urgent": True, "category": None}),
    )
    result = next_step(case)
    assert result["urgent"] and not result["card_ready"]
    assert result["questions"] == [EMERGENCY_REPLY] and result["proposed_facts"] == []


@override_settings(LLM_PROVIDER="openai")
def test_live_provider_blocks_case_data_before_transmission(case, monkeypatch):
    message(case, "личная информация")
    provider = Mock(side_effect=AssertionError("must not transmit case data"))
    monkeypatch.setattr("apps.cases.intake.complete_json", provider)
    with pytest.raises(LLMError, match="disabled"):
        next_step(case)
    provider.assert_not_called()
