import pytest

from apps.pool.pii import KnownPersonalData, amount_range, date_to_month, scan

PERSON = KnownPersonalData(
    names=("Иванов Иван Иванович",),
    addresses=("Лесной тупик 19",),
    contract_numbers=("AB-87203",),
    passport_numbers=("4512 123456",),
)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Позвоните +7 (921) 123-45-67", "phone"),
        ("Телефон 8 921 123 45 67", "phone"),
        ("Телефон 79211234567", "phone"),
        ("Телефон 9211234567", "phone"),
        ("Звоните 921 123-45-67", "phone"),
        ("Телефон 8-921-123-45-67", "phone"),
        ("Телефон +7.921.123.45.67", "phone"),
        ("Почта jane@example.org", "email"),
        ("Email a.b+tag@example.co.uk", "email"),
        ("Почта USER_1@example.ru", "email"),
        ("Карта 1234567890123", "card"),
        ("Карта 123456789012345", "card"),
        ("Карта 1234 5678 9012 3456", "card"),
        ("Карта 1234-5678-9012-3456", "card"),
        ("Карта 1234567890123456", "card"),
        ("Номер 1234 5678 9012 3456 789", "card"),
        ("договор № 123-ABC", "contract"),
        ("по договору 12345", "contract"),
        ("договор от 12345", "contract"),
        ("договор N 12345", "contract"),
        ("Номер договора AB-87203", "contract"),
        ("Номер договора ZX-45", "contract"),
        ("по договору номер 12345", "contract"),
        ("контракт #AA-15", "contract"),
        ("подписал Иван Иванович", "name"),
        ("документ Иванова", "name"),
        ("передал Иванову", "name"),
        ("подписано Ивановым", "name"),
        ("связались с Иваном", "name"),
        ("дом Лесной тупик 19", "address"),
        ("адрес: ул. Лесная, д. 14", "address"),
        ("улица Лесная 14", "address"),
        ("пр. Ленина, д. 5", "address"),
        ("г. Москва, Ленина, 5, кв. 7", "address"),
        ("переулок Луговой дом 13", "address"),
        ("паспорт 4512 123456", "passport"),
        ("паспорт серия 45 12 номер 123456", "passport"),
        ("серия и номер 4512 123456", "passport"),
        ("платёж 15.02.2025", "date"),
        ("15/02/2025 передал заявление", "date"),
        ("дата 15-02-2025", "date"),
        ("2025-02-15", "date"),
        ("15 февраля 2025 года", "date"),
        ("1 марта 2025 г.", "date"),
        ("15 ФЕВРАЛЯ 2025", "date"),
        ("дата: 1.3.2025", "date"),
    ],
)
def test_detects_personal_data(text, kind):
    assert kind in {finding.kind for finding in scan(text, PERSON)}


@pytest.mark.parametrize(
    "text",
    [
        "Компания Ромашка работает в Москве",
        "ООО Северная звезда, Санкт-Петербург",
        "Компания Точка и город Нижний Новгород",
        "Потребитель обратился в Казани в феврале 2025 года",
        "Сумма спора 50000 рублей, ответ не получен",
        "Дата: февраль 2025",
    ],
)
def test_company_and_city_do_not_trigger(text):
    assert scan(text, PERSON) == []


def test_results_do_not_contain_private_text_or_log_it(caplog):
    value = "jane@example.org"
    result = scan(value, PERSON)
    assert result[0].kind == "email"
    assert value not in repr(result)
    assert value not in caplog.text
    assert "Иванов" not in repr(PERSON)


def test_known_personal_data_does_not_become_automatic_public_allowlist():
    assert scan("Компания Иванов", PERSON)


@pytest.mark.parametrize(
    ("known_name", "text"),
    [
        ("Петровский", "Заявление Петровского"),
        ("Петровский", "Передали Петровскому"),
        ("Петровский", "Подписано Петровским"),
        ("Петровский", "Сведения о Петровском"),
        ("Петровская", "Документы Петровской"),
        ("Петровская", "Обратились к Петровской"),
        ("Петровская", "Уведомили Петровскую"),
    ],
)
def test_adjectival_surname_case_endings(known_name, text):
    result = scan(text, KnownPersonalData(names=(known_name,)))
    assert len(result) == 1
    assert result[0].kind == "name"
    assert text[result[0].start : result[0].end] == text.split()[-1]


@pytest.mark.parametrize("known_name", ["Петровский", "Петровская"])
@pytest.mark.parametrize(
    "text",
    [
        "Компания Петровские технологии, город Петровск",
        "АО Петровскмаш работает в Москве",
    ],
)
def test_surname_stem_does_not_match_city_or_company(known_name, text):
    assert scan(text, KnownPersonalData(names=(known_name,))) == []


@pytest.mark.parametrize("bad", [None, {}, 12, "данные"])
def test_invalid_known_data_fails_closed(bad):
    with pytest.raises(ValueError):
        scan("пример", bad)


def test_unsupported_short_name_fails_closed():
    with pytest.raises(ValueError):
        scan("Ким", KnownPersonalData(names=("Ким",)))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-02-29", "2024-02"),
        ("2025-2-5", "2025-02"),
        ("29.02.2024", "2024-02"),
        ("15/02/2025", "2025-02"),
        ("1-3-2025", "2025-03"),
        ("1 марта 2025 года", "2025-03"),
    ],
)
def test_date_becomes_month(value, expected):
    assert date_to_month(value) == expected


@pytest.mark.parametrize("value", ["2025-02-29", "31.04.2025", "01/02-2025", "февраль 2025", ""])
def test_ambiguous_or_invalid_date_fails_closed(value):
    with pytest.raises(ValueError):
        date_to_month(value)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, (0, 999_999)),
        (999_999, (0, 999_999)),
        (1_000_000, (1_000_000, 4_999_999)),
        (4_999_999, (1_000_000, 4_999_999)),
        (5_000_000, (5_000_000, 9_999_999)),
        (10_000_000, (10_000_000, 49_999_999)),
        (50_000_000, (50_000_000, 99_999_999)),
        (100_000_000, (100_000_000, 199_999_999)),
        (199_999_999, (100_000_000, 199_999_999)),
        (200_000_000, (200_000_000, 299_999_999)),
    ],
)
def test_amount_range_boundaries(amount, expected):
    result = amount_range(amount)
    assert (result["min_kopecks"], result["max_kopecks"]) == expected
    assert result["min_kopecks"] <= amount <= result["max_kopecks"]


@pytest.mark.parametrize("amount", [-1, 1.5, True, "100"])
def test_invalid_amount_fails_closed(amount):
    with pytest.raises(ValueError):
        amount_range(amount)
