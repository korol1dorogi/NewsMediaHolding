from datetime import date

import pytest

from apps.guidance.deadlines import DeadlinePolicy, article_31_deadline, calculate_deadline
from apps.guidance.destinations import DESTINATIONS
from apps.guidance.norms import select_norms
from apps.guidance.templates import InvalidFact, MissingFacts, render_document, required_fields


def approved_test_policy(days):
    return DeadlinePolicy(True, days, "calendar_days", "day_after_event", "next_working_day")


def working_weekdays(day):
    return day.weekday() < 5


@pytest.mark.parametrize(
    ("event", "period", "expected"),
    [
        (date(2024, 2, 28), 1, date(2024, 2, 29)),
        (date(2024, 12, 31), 1, date(2025, 1, 1)),
        (date(2025, 1, 31), 1, date(2025, 2, 3)),
    ],
)
def test_deadline_arithmetic_with_explicit_calendar(event, period, expected):
    result = calculate_deadline(
        event, policy=approved_test_policy(period), calendar=working_weekdays
    )
    assert result.due_on == expected
    assert result.reason is None


def test_holiday_calendar_is_supplied_by_caller():
    holidays = {date(2025, 1, 1)}
    calendar = lambda day: day.weekday() < 5 and day not in holidays  # noqa: E731
    result = calculate_deadline(
        date(2024, 12, 31), policy=approved_test_policy(1), calendar=calendar
    )
    assert result.due_on == date(2025, 1, 2)


@pytest.mark.parametrize(
    ("event", "period", "confirmed", "calendar", "reason"),
    [
        (date(2025, 1, 1), 10, False, working_weekdays, "policy_unconfirmed"),
        (None, 10, True, working_weekdays, "event_date_unknown"),
        (date(2025, 1, 1), None, True, working_weekdays, "period_unknown"),
        (date(2025, 1, 1), 10, True, None, "calendar_unknown"),
        (date(2025, 1, 1), 10, True, lambda day: None, "calendar_unknown"),
        (date.max, 10, True, working_weekdays, "date_out_of_range"),
    ],
)
def test_deadline_unknown_never_becomes_zero(event, period, confirmed, calendar, reason):
    policy = DeadlinePolicy(
        confirmed, period, "calendar_days", "day_after_event", "next_working_day"
    )
    result = calculate_deadline(event, policy=policy, calendar=calendar)
    assert result.due_on is None
    assert result.reason == reason


def test_norms_require_confirmed_conditions_and_are_not_lawyer_verified():
    assert select_norms({"consumer", "paid_service"}) == []
    norms = select_norms({"consumer", "paid_service", "refusal"})
    assert [norm["id"] for norm in norms] == ["consumer_services_refusal_32"]
    assert all(norm["url"].startswith("https://zpp.rospotrebnadzor.ru/") for norm in norms)
    assert all(norm["verified_by_lawyer"] is False for norm in norms)
    assert select_norms({"consumer", "paid_service", "refusal"}) == norms


EXAMPLES = {
    "claim": {
        "company_name": "Учебный проект Демо",
        "service_description": "Онлайн-курс Демо",
        "payment_date": "2025-01-10",
        "amount_kopecks": 6800000,
        "claim_amount_kopecks": 4000000,
        "circumstances": "Заявитель попросил прекратить обучение",
    },
    "bank": {
        "bank_name": "Демо Банк",
        "merchant_name": "Учебный проект Демо",
        "transaction_date": "2025-01-10",
        "amount_kopecks": 6800000,
        "circumstances": "Услуга не предоставлена в полном объёме",
        "request": "рассмотреть возможность оспаривания операции",
    },
    "consumer_authority": {
        "authority_name": "Территориальное управление Роспотребнадзора",
        "company_name": "Учебный проект Демо",
        "service_description": "Онлайн-курс Демо",
        "payment_date": "2025-01-10",
        "amount_kopecks": 6800000,
        "claim_date": "2025-02-01",
        "circumstances": "Заявитель просил вернуть деньги",
        "request": "рассмотреть обращение",
    },
}


@pytest.mark.parametrize("kind", ["claim", "bank", "consumer_authority"])
def test_document_requires_every_specified_fact(kind):
    for key in required_fields(kind):
        facts = {name: value for name, value in EXAMPLES[kind].items() if name != key}
        with pytest.raises(MissingFacts) as exc:
            render_document(kind, facts)
        assert exc.value.names == (key,)
        assert "Учебный проект Демо" not in str(exc.value)


@pytest.mark.parametrize("kind", ["claim", "bank", "consumer_authority"])
def test_render_synthetic_draft_without_personal_data(kind, caplog):
    result = render_document(kind, EXAMPLES[kind])
    assert result.verified_by_lawyer is False
    assert "не проверено юристом" in result.template_text
    assert "{{claimant}}" in result.template_text
    assert "{{reply_address}}" in result.template_text
    assert "68000.00 руб." in result.template_text
    assert DESTINATIONS[kind]
    assert "Учебный проект Демо" not in caplog.text


@pytest.mark.parametrize(
    "injection",
    [
        "{{claimant}}",
        "{{unknown}}",
        "{% raw %}",
        "${amount_rub}",
        "<% malicious %>",
        "\nНовая строка",
    ],
)
def test_template_injection_fails_without_echoing_data(injection, caplog):
    facts = dict(EXAMPLES["claim"], circumstances=injection)
    with pytest.raises(InvalidFact) as exc:
        render_document("claim", facts)
    assert exc.value.name == "circumstances"
    assert injection not in str(exc.value)
    assert injection not in caplog.text


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "6800000"])
def test_amount_is_positive_integer_kopecks(value):
    with pytest.raises(InvalidFact):
        render_document("claim", dict(EXAMPLES["claim"], amount_kopecks=value))


def test_explicit_personal_data_fields_are_rejected():
    facts = dict(EXAMPLES["claim"], claimant="Секретное имя")
    with pytest.raises(ValueError, match="Unexpected fact fields") as exc:
        render_document("claim", facts)
    assert "Секретное имя" not in str(exc.value)


def test_article_31_requires_explicit_applicability_and_policy():
    date_presented = date(2024, 2, 28)
    unknown = article_31_deadline(
        presented_on=date_presented, applicable=None, calendar=working_weekdays
    )
    assert unknown.due_on is None
    assert unknown.reason == "article_31_applicability_unconfirmed"
    unapproved = article_31_deadline(
        presented_on=date_presented, applicable=True, calendar=working_weekdays
    )
    assert unapproved.due_on is None
    assert unapproved.reason == "policy_unconfirmed"
    confirmed = article_31_deadline(
        presented_on=date_presented,
        applicable=True,
        calendar=working_weekdays,
        policy_approved=True,
    )
    assert confirmed.due_on == date(2024, 3, 11)
    assert confirmed.verified_by_lawyer is False


def test_unsupported_or_unapproved_policy_is_never_applied():
    event = date(2025, 1, 1)
    assert (
        calculate_deadline(event, policy=None, calendar=working_weekdays).reason
        == "policy_unconfirmed"
    )
    unsupported = DeadlinePolicy(True, 10, "business_days", "day_after_event", "next_working_day")
    assert (
        calculate_deadline(event, policy=unsupported, calendar=working_weekdays).reason
        == "policy_unsupported"
    )


def test_date_must_exist_and_error_contains_no_submitted_value():
    facts = dict(EXAMPLES["claim"], payment_date="2025-02-29")
    with pytest.raises(InvalidFact) as exc:
        render_document("claim", facts)
    assert exc.value.name == "payment_date"
    assert "2025-02-29" not in str(exc.value)


def test_all_norms_link_official_sources_and_stay_unverified():
    norms = select_norms({"consumer", "paid_service", "refusal", "article_31_applicable"})
    assert len(norms) == 2
    assert all(norm["url"].startswith("https://zpp.rospotrebnadzor.ru/") for norm in norms)
    assert all(norm["verified_by_lawyer"] is False for norm in norms)


def test_free_text_may_contain_personal_data_and_is_not_logged(caplog):
    personal_data = "Для связи: Иван Примеров"
    draft = render_document("claim", dict(EXAMPLES["claim"], circumstances=personal_data))
    assert personal_data in draft.template_text
    assert personal_data not in caplog.text
