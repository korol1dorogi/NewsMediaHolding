"""B4: three paths, availability by company status and case state, the self-guided plan."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.cases.models import Case
from apps.cases.testing import ANYA_FACTS, confirmed_case, make_user
from apps.companies import providers
from apps.guidance import deadlines

pytestmark = pytest.mark.django_db

LIBRARY_IDS = {
    norm["id"]
    for norm in json.loads(
        (Path(deadlines.__file__).parent / "resources" / "norms.json").read_text(encoding="utf-8")
    )
}


@pytest.fixture
def owner():
    return make_user("owner")


@pytest.fixture
def client(owner):
    client = APIClient()
    client.force_login(owner)
    return client


def company(status):
    fixture = {"status": status, "name": "Учебный проект Демо", "registered_on": "2020-01-15"}
    return patch.dict(providers.MOCK_FIXTURES, {"0000000000": fixture})


def paths(client, case):
    response = client.get(f"/api/cases/{case.pk}/paths")
    assert response.status_code == 200, response.data
    return {item["path"]: item for item in response.json()["items"]}


def test_three_paths_for_active_company(client, owner, settings):
    settings.PAYMENTS_CLAIM_PRICE_KOPECKS = 149_000
    result = paths(client, confirmed_case(owner))
    assert list(result) == ["self_guided", "claim", "specialist"]
    assert all(item["available"] for item in result.values())
    assert result["self_guided"]["price_kopecks"] == 0
    assert result["claim"]["price_kopecks"] == 149_000
    assert result["specialist"]["price_kopecks"] is None
    assert result["specialist"]["estimated_days"] == 2


@pytest.mark.parametrize(
    ("status", "words"),
    [
        ("liquidating", "ликвидационной комиссии"),
        ("bankrupt", "деле о банкротстве"),
        ("unavailable", "Не удалось проверить"),
    ],
)
def test_claim_only_for_active_company(client, owner, status, words):
    if status == "unavailable":
        case = confirmed_case(owner, {**ANYA_FACTS, "company_inn": "1234567890"})
        result = paths(client, case)
    else:
        with company(status):
            result = paths(client, confirmed_case(owner))
    assert result["claim"]["available"] is False
    assert words in result["claim"]["reason"]
    assert result["self_guided"]["available"] is True
    assert result["specialist"]["available"] is True
    if status == "unavailable":
        assert result["self_guided"]["reason"]


def test_paths_before_confirmation_are_409(client, owner):
    case = Case.objects.create(owner=owner, state="card_ready", consent_text_version="v1")
    for suffix in ("paths", "plan", "company"):
        assert client.get(f"/api/cases/{case.pk}/{suffix}").status_code == 409
    response = client.post(
        f"/api/cases/{case.pk}/path", {"path": "self_guided", "expected_version": 1}, format="json"
    )
    assert response.status_code == 409


def choose(client, case, path):
    case.refresh_from_db()
    return client.post(
        f"/api/cases/{case.pk}/path",
        {"path": path, "expected_version": case.version},
        format="json",
    )


@pytest.mark.parametrize(
    ("path", "state"),
    [("self_guided", "self_guided"), ("claim", "claim_draft"), ("specialist", "in_pool")],
)
def test_choose_path_transitions(client, owner, path, state):
    case = confirmed_case(owner)
    response = choose(client, case, path)
    assert response.status_code == 200, response.data
    assert response.data["state"] == state
    assert response.data["path"] == path
    assert response.data["version"] == case.version + 1


def test_self_guided_then_claim_then_no_repeat(client, owner):
    case = confirmed_case(owner)
    assert choose(client, case, "self_guided").status_code == 200
    assert choose(client, case, "self_guided").status_code == 409
    assert choose(client, case, "claim").data["state"] == "claim_draft"
    assert choose(client, case, "specialist").status_code == 409


def test_unavailable_claim_cannot_be_chosen(client, owner):
    with company("bankrupt"):
        case = confirmed_case(owner)
        response = choose(client, case, "claim")
    assert response.status_code == 409
    assert response.data["details"] == {"fields": ["path"]}
    case.refresh_from_db()
    assert case.state == "card_confirmed"


def test_stale_version_and_bad_input(client, owner):
    case = confirmed_case(owner)
    url = f"/api/cases/{case.pk}/path"
    stale = {"path": "self_guided", "expected_version": case.version + 5}
    assert client.post(url, stale, format="json").status_code == 409
    bad = {"path": "court", "expected_version": case.version}
    assert client.post(url, bad, format="json").status_code == 400
    forged = {"path": "self_guided", "expected_version": case.version, "state": "completed"}
    assert client.post(url, forged, format="json").status_code == 400


def test_plan_for_active_company(client, owner):
    case = confirmed_case(owner)
    plan = client.get(f"/api/cases/{case.pk}/plan").json()
    assert plan["version"] == case.card_version
    assert plan["disclaimer"]
    orders = [step["order"] for step in plan["steps"]]
    assert orders == list(range(1, len(orders) + 1))
    text = " ".join(step["text"] for step in plan["steps"])
    assert "68 000 ₽" in text
    assert "Учебный проект Демо" in text
    norms = [norm for step in plan["steps"] for norm in step["norms"]]
    assert norms, "the claim step cites the library norm"
    assert {norm["id"] for norm in norms} <= LIBRARY_IDS
    assert all(norm["verified_by_lawyer"] is False for norm in norms)
    # Deadline policy is not approved by lawyers: no invented dates.
    assert all(step["due_on"] is None for step in plan["steps"])
    assert "01.10.2026" in " ".join(" ".join(step["documents"]) for step in plan["steps"])


@pytest.mark.parametrize(
    ("status", "destination"),
    [
        ("bankrupt", "Арбитражный управляющий"),
        ("liquidating", "Ликвидационная комиссия"),
    ],
)
def test_plan_for_insolvent_company(client, owner, status, destination):
    with company(status):
        case = confirmed_case(owner)
        plan = client.get(f"/api/cases/{case.pk}/plan").json()
    destinations = [step["destination"] for step in plan["steps"]]
    assert any(destination in item for item in destinations)
    assert not any(step["norms"] for step in plan["steps"])


def test_plan_without_amount_has_no_norms_and_no_invented_sum(client, owner):
    facts = {k: v for k, v in ANYA_FACTS.items() if k != "amount"}
    case = confirmed_case(owner, facts)
    plan = client.get(f"/api/cases/{case.pk}/plan").json()
    text = " ".join(step["text"] for step in plan["steps"])
    assert "₽" not in text
    assert not any(step["norms"] for step in plan["steps"])


def test_plan_is_stable_for_the_same_snapshot(client, owner):
    case = confirmed_case(owner)
    first = client.get(f"/api/cases/{case.pk}/plan").json()
    case.facts.update(value="changed live row")
    assert client.get(f"/api/cases/{case.pk}/plan").json() == first


def test_foreign_case_is_404(owner):
    case = confirmed_case(owner)
    stranger = APIClient()
    stranger.force_login(make_user("stranger"))
    for suffix in ("paths", "plan"):
        assert stranger.get(f"/api/cases/{case.pk}/{suffix}").status_code == 404
    response = stranger.post(
        f"/api/cases/{case.pk}/path",
        {"path": "self_guided", "expected_version": case.version},
        format="json",
    )
    assert response.status_code == 404
