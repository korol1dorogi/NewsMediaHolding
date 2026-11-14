from dataclasses import replace
from traceback import format_exception
from unittest.mock import Mock

import pytest
from django.test import override_settings

from apps.pool import anonymize as service
from apps.pool.pii import KnownPersonalData


@pytest.fixture
def case():
    return service.MockCaseAdapter(
        scenario="anya",
        category="education",
        city="Вымышленный город",
        amount_range={"min_kopecks": 5_000_000, "max_kopecks": 9_999_999},
        company={"name": "Учебный проект Демо", "status": "active"},
        actions_taken=["Запрошен возврат оплаты"],
        similar_cases={"count": 0, "cities_count": 0, "period_months": 12},
        source_description="Иванова Анна, телефон +7 (999) 123-45-67: возврат за курс.",
        personal_data=KnownPersonalData(names=("Иванова Анна Сергеевна",)),
    )


@override_settings(LLM_PROVIDER="mock")
def test_anya_mock_is_deterministic_and_preserves_only_trusted_fields(case, monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", Mock(side_effect=AssertionError("network is forbidden"))
    )
    draft = service.anonymize(case)
    assert draft == service.anonymize(case)
    assert set(draft) == {
        "category",
        "description",
        "city",
        "amount_range",
        "company",
        "actions_taken",
        "similar_cases",
    }
    assert draft["category"] == case.category
    assert draft["amount_range"] == case.amount_range
    assert draft["company"] == case.company
    assert draft["actions_taken"] == case.actions_taken
    assert draft["similar_cases"] == case.similar_cases
    assert "Иванова" not in repr(draft)
    assert "+7 (999) 123-45-67" not in repr(draft)
    assert case.source_description not in repr(case)


def test_adapter_representation_hides_all_caller_data(case):
    case = replace(
        case,
        scenario="private-scenario",
        category="private-category",
        city="private-city",
        company={"name": "private-company", "status": "active"},
        actions_taken=["private-action"],
        similar_cases={"count": 923456789012345678, "cities_count": 12, "period_months": 45},
    )
    representation = repr(case)
    for marker in ("private-", "923456789012345678", "Иванова", "+7 (999)"):
        assert marker not in representation


@override_settings(LLM_PROVIDER="mock")
@pytest.mark.parametrize("leak", ["Иванова", "+7 (999) 123-45-67"])
def test_personal_data_in_description_retries_and_never_returns_unsafe_result(
    case, monkeypatch, caplog, leak
):
    provider = Mock(return_value=f"Текст с данными {leak}")
    monkeypatch.setattr(service, "_mock_description", provider)
    with pytest.raises(service.UnsafeOutput) as error:
        service.anonymize(case)
    assert provider.call_count == 2
    assert leak not in str(error.value)
    assert leak not in caplog.text


@override_settings(LLM_PROVIDER="mock")
def test_unsafe_first_description_is_not_returned_when_retry_is_safe(case, monkeypatch):
    provider = Mock(side_effect=["Телефон +7 (999) 123-45-67", "Безопасное описание"])
    monkeypatch.setattr(service, "_mock_description", provider)
    draft = service.anonymize(case)
    assert draft["description"] == "Безопасное описание"
    assert provider.call_count == 2


@override_settings(LLM_PROVIDER="mock")
@pytest.mark.parametrize(
    "updates",
    [
        {"category": "Иванова"},
        {"city": "улица Лесная 14"},
        {"company": {"name": "Контакт +7 (999) 123-45-67", "status": "active"}},
        {"actions_taken": ["Почта jane@example.org"]},
    ],
)
def test_all_public_string_fields_are_scanned(case, updates):
    with pytest.raises(service.UnsafeOutput):
        service.anonymize(replace(case, **updates))


@override_settings(LLM_PROVIDER="mock")
def test_scanner_errors_fail_closed_without_disclosing_details(case, monkeypatch):
    scanner = Mock(side_effect=RuntimeError("private synthetic text"))
    monkeypatch.setattr(service, "scan", scanner)
    with pytest.raises(service.UnsafeOutput) as error:
        service.anonymize(case)
    assert "private synthetic text" not in str(error.value)
    assert "private synthetic text" not in "".join(format_exception(error.value))
    assert error.value.__suppress_context__


@override_settings(LLM_PROVIDER="openai")
def test_real_provider_is_not_called(case, monkeypatch):
    provider = Mock(side_effect=AssertionError("must not invoke a real provider"))
    monkeypatch.setattr(service, "_mock_description", provider)
    with pytest.raises(service.InvalidOutput):
        service.anonymize(case)
    provider.assert_not_called()


@override_settings(LLM_PROVIDER="mock")
def test_unknown_mock_scenario_fails_without_fabricating_a_result(case):
    with pytest.raises(service.InvalidOutput):
        service.anonymize(replace(case, scenario="unknown"))


@override_settings(LLM_PROVIDER="mock")
@pytest.mark.parametrize(
    "updates",
    [
        {"company": {"name": "Компания", "status": "invented"}},
        {"amount_range": {"min_kopecks": 100, "max_kopecks": 99}},
        {"similar_cases": {"count": 1, "cities_count": 1}},
    ],
)
def test_missing_or_invalid_trusted_values_fail(case, updates):
    with pytest.raises(service.InvalidOutput):
        service.anonymize(replace(case, **updates))
