from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.cases.testing import ANYA_FACTS, confirmed_case, make_user
from apps.companies import providers, services
from apps.companies.inn import normalize_inn
from apps.companies.models import CompanyCheck

pytestmark = pytest.mark.django_db

# Checksum-valid numbers used only inside tests with a patched mock cache. They are never
# sent to a real registry (the mock provider has no network access).
VALID_10 = "7707083893"
VALID_12 = "500100732259"


@pytest.mark.parametrize("inn", [VALID_10, VALID_12, "0000000000", " 7707083893 "])
def test_valid_inn(inn):
    assert normalize_inn(inn) == inn.strip()


@pytest.mark.parametrize(
    "inn", ["7707083894", "500100732258", "123", "77070838931", "abcdefghij", "٧٧٠٧٠٨٣٨٩٣", None]
)
def test_invalid_inn(inn):
    assert normalize_inn(inn) is None


def test_check_rejects_invalid_inn_before_provider():
    with patch.dict(providers.PROVIDERS, {"mock": pytest.fail}), pytest.raises(services.InvalidInn):
        services.check("1234567890")


@pytest.mark.parametrize("status", ["active", "liquidating", "bankrupt"])
def test_mock_statuses(status):
    fixture = {"status": status, "name": "Тест", "registered_on": "2020-01-01"}
    with patch.dict(providers.MOCK_FIXTURES, {VALID_10: fixture}):
        result = services.check(VALID_10)
    assert result["status"] == status
    assert result["inn"] == VALID_10
    assert result["is_demo"] is False


def test_demo_sentinel_is_demo_company():
    result = services.check("0000000000")
    assert result == {
        "status": "active",
        "name": "Учебный проект Демо",
        "registered_on": "2020-01-15",
        "source": "demo-fixture",
        "is_demo": True,
        "inn": "0000000000",
    }


def test_unknown_company_in_mock_is_unavailable_not_active():
    assert services.check(VALID_10)["status"] == "unavailable"


def test_provider_failure_is_unavailable(settings):
    settings.COMPANIES_PROVIDER = "dadata"
    settings.COMPANIES_API_KEY = "test-key"
    with patch.object(providers.request, "urlopen", side_effect=OSError("down")):
        result = services.check(VALID_10)
    assert result["status"] == "unavailable"
    assert result["source"] == "dadata"


def test_real_provider_never_receives_demo_sentinel(settings):
    settings.COMPANIES_PROVIDER = "dadata"
    settings.COMPANIES_API_KEY = "test-key"
    with patch.object(providers.request, "urlopen", side_effect=AssertionError):
        assert services.check("0000000000")["status"] == "unavailable"


def test_real_provider_without_key_is_unavailable(settings):
    settings.COMPANIES_PROVIDER = "dadata"
    settings.COMPANIES_API_KEY = ""
    with patch.object(providers.request, "urlopen", side_effect=AssertionError):
        assert services.check(VALID_10)["status"] == "unavailable"


@pytest.fixture
def owner():
    return make_user("owner")


@pytest.fixture
def client(owner):
    client = APIClient()
    client.force_login(owner)
    return client


def test_endpoint_returns_and_stores_snapshot(client, owner):
    case = confirmed_case(owner)
    response = client.get(f"/api/cases/{case.pk}/company")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["inn"] == "0000000000"
    assert body["is_demo"] is True
    assert body["checked_at"].endswith("Z")
    assert CompanyCheck.objects.filter(case=case).count() == 1
    # A repeated read reuses the stored snapshot instead of calling the registry again.
    with patch.dict(providers.PROVIDERS, {"mock": pytest.fail}):
        assert client.get(f"/api/cases/{case.pk}/company").json() == body
    assert CompanyCheck.objects.filter(case=case).count() == 1


@pytest.mark.parametrize(("inn", "source"), [(None, "inn_missing"), ("1234567890", "inn_invalid")])
def test_card_without_valid_inn_is_unavailable(client, owner, inn, source):
    facts = {k: v for k, v in ANYA_FACTS.items() if k != "company_inn"}
    if inn:
        facts["company_inn"] = inn
    case = confirmed_case(owner, facts)
    body = client.get(f"/api/cases/{case.pk}/company").json()
    assert body["status"] == "unavailable"
    assert body["source"] == source
    assert body["name"] == ANYA_FACTS["company_name"]
    assert body["inn"] is None


def test_unconfirmed_card_is_409(client, owner):
    case = confirmed_case(owner)
    case.card_confirmed_at = None
    case.state = "card_ready"
    case.save()
    assert client.get(f"/api/cases/{case.pk}/company").status_code == 409


def test_foreign_case_is_404(owner):
    case = confirmed_case(owner)
    for role in ("user", "lawyer"):
        stranger = APIClient()
        stranger.force_login(make_user(f"stranger-{role}", role=role))
        assert stranger.get(f"/api/cases/{case.pk}/company").status_code == 404
    assert APIClient().get(f"/api/cases/{case.pk}/company").status_code == 401
