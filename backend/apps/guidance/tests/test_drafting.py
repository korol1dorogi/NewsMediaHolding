"""A4: the model writes prose only; code checks it and fills in everything else."""

from unittest.mock import patch

import pytest

from apps.cases.testing import ANYA_FACTS, confirmed_case, make_user
from apps.guidance import drafting
from apps.guidance.templates import MissingFacts

pytestmark = pytest.mark.django_db

ALLOWED = drafting._allowed_numbers(6_800_000, __import__("datetime").date(2026, 10, 1))


@pytest.fixture
def case():
    return confirmed_case(make_user("owner"))


def test_anya_draft_on_mock_is_complete(case):
    result = drafting.draft_claim(case)
    text = result["template_text"]
    assert result["input_card_version"] == case.card_version
    assert "Учебный проект Демо" in text
    assert "онлайн-курс по программированию" in text
    assert "01.10.2026" in text
    assert "68000.00 руб." in text
    assert "Исполнитель не оказал оплаченную услугу" in text
    # Personal data stays as placeholders; B5 fills them for the owner only.
    assert "{{claimant}}" in text and "{{reply_address}}" in text
    assert result["norm_ids"] == ["consumer_services_refusal_32"]
    assert "статья 32" in text
    assert "не проверено юристом" in text


@pytest.mark.parametrize(
    "text",
    [
        "Исполнитель нарушил статью 29 закона и не вернул деньги потребителю",
        "Согласно ст. 15 исполнитель обязан вернуть деньги потребителю полностью",
        "По ГК исполнитель обязан вернуть деньги потребителю в полном объёме",
        "Исполнитель нарушил ЗоЗПП и не вернул деньги потребителю за курс",
    ],
)
def test_legal_reference_outside_library_is_rejected(text):
    with pytest.raises(drafting.InvalidOutput):
        drafting.check_text(text, ALLOWED)


@pytest.mark.parametrize(
    "text",
    [
        "Потребитель оплатил 70000 рублей, но исполнитель не оказал услугу вовсе",
        "Потребитель оплатил курс 5 октября, но исполнитель не оказал услугу",
        "Оплата прошла 02.10.2026, однако исполнитель не оказал услугу вовсе",
        "Потребитель оплатил курс в 2025 году, но исполнитель не оказал услугу",
    ],
)
def test_amount_or_date_not_on_card_is_rejected(text):
    with pytest.raises(drafting.InvalidOutput):
        drafting.check_text(text, ALLOWED)


def test_numbers_from_card_are_allowed():
    text = "Потребитель оплатил 68 000 рублей 1 октября 2026 года, услуга не оказана"
    assert drafting.check_text(text, ALLOWED) == text


def test_promise_is_rejected():
    with pytest.raises(drafting.InvalidOutput):
        drafting.check_text(
            "Деньги гарантированно вернут после этой претензии потребителю", ALLOWED
        )


def test_bad_model_answer_is_retried_once_then_fails(case):
    bad = {"circumstances": "Исполнитель нарушил статью 29 и должен вернуть все деньги"}
    with patch.object(drafting, "complete_json", return_value=bad) as model:
        with pytest.raises(drafting.InvalidOutput):
            drafting.draft_claim(case)
    assert model.call_count == 2


def test_retry_can_succeed(case):
    bad = {"circumstances": "Исполнитель нарушил статью 29 и должен вернуть все деньги"}
    good = {"circumstances": "Исполнитель не оказал услугу и не вернул деньги потребителю"}
    with patch.object(drafting, "complete_json", side_effect=[bad, good]):
        assert "не оказал услугу" in drafting.draft_claim(case)["template_text"]


@pytest.mark.parametrize(
    ("missing", "value"),
    [("amount", None), ("amount", "сколько-то"), ("payment_date", "давно"), ("company_name", None)],
)
def test_missing_or_unparsable_facts_are_named(missing, value):
    facts = {k: v for k, v in ANYA_FACTS.items() if k != missing}
    if value:
        facts[missing] = value
    case = confirmed_case(make_user("owner"), facts)
    assert drafting.missing_facts(case) == [missing]
    with pytest.raises(MissingFacts) as error:
        drafting.draft_claim(case)
    assert error.value.names == (missing,)


def test_unconfirmed_card_is_rejected(case):
    case.card_confirmed_at = None
    with pytest.raises(drafting.UnconfirmedCard):
        drafting.draft_claim(case)
