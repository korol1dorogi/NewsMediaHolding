"""B5: draft, versions, personal data kept apart, submit for review (no payment in wave 2)."""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.cases.testing import ANYA_FACTS, confirmed_case, make_user
from apps.claims import tasks
from apps.claims.models import Claim, ClaimPersonalData, ClaimVersion

pytestmark = pytest.mark.django_db

PERSONAL = {
    "full_name": "Демо Пользователь",
    "reply_address": "Вымышленный город, учебный адрес",
    "contract_reference": "DEMO-CONTRACT-1",
}
CONSENT = {"accepted": True, "text_version": "demo-v1"}


@pytest.fixture
def owner():
    return make_user("owner")


@pytest.fixture
def client(owner):
    client = APIClient()
    client.force_login(owner)
    return client


@pytest.fixture
def case(owner):
    return confirmed_case(owner, state="claim_draft")


@pytest.fixture
def run_tasks(django_capture_on_commit_callbacks):
    with patch.object(tasks.make_draft, "delay", side_effect=tasks.make_draft.run):
        yield django_capture_on_commit_callbacks


def url(case, suffix=""):
    return f"/api/cases/{case.pk}/claim{suffix}"


def create(client, case, run_tasks):
    case.refresh_from_db()
    with run_tasks(execute=True):
        response = client.post(url(case), {"expected_version": case.version}, format="json")
    return response


def detail(client, case):
    return client.get(f"/api/cases/{case.pk}").json()


def test_full_wave2_flow(client, case, run_tasks):
    assert detail(client, case)["available_actions"] == ["create_claim", "close_case"]
    response = create(client, case, run_tasks)
    assert response.status_code == 202
    assert response.data["case"]["ai_state"] == "thinking"
    claim_id = response.data["claim_id"]

    claim = client.get(url(case)).json()
    assert claim["id"] == claim_id
    assert claim["current_version"] == 1
    assert claim["versions"][0]["author"] == "ai"
    assert claim["versions"][0]["comment"] is None
    assert "{{claimant}}" in claim["versions"][0]["text"]
    assert claim["personal_data"] is None and claim["personal_data_confirmed"] is False
    assert claim["available_actions"] == ["confirm_personal_data", "close_case"]

    put = client.put(
        url(case, "/personal-data"),
        {"expected_version": claim["case_version"], "data": PERSONAL, "confirmed": True},
        format="json",
    )
    assert put.status_code == 200, put.data
    claim = put.json()
    assert claim["personal_data"] == PERSONAL
    assert "Демо Пользователь" in claim["versions"][0]["text"]
    assert "{{claimant}}" not in claim["versions"][0]["text"]
    assert claim["available_actions"] == ["confirm_personal_data", "submit_claim", "close_case"]
    # The stored version keeps placeholders: personal data is only substituted on read.
    assert "{{claimant}}" in ClaimVersion.objects.get().template_text

    submit = client.post(
        url(case, "/submit"),
        {"expected_version": claim["case_version"], "claim_version": 1, "consent": CONSENT},
        format="json",
    )
    assert submit.status_code == 200, submit.data
    assert submit.data["state"] == "claim_in_review"
    stored = Claim.objects.get()
    assert stored.submitted_at is not None
    assert stored.submit_consent_version == "demo-v1"


def test_get_before_ready_is_409_and_without_claim_404(
    client, case, django_capture_on_commit_callbacks
):
    assert client.get(url(case)).status_code == 404
    with django_capture_on_commit_callbacks(execute=False):
        assert (
            client.post(url(case), {"expected_version": case.version}, format="json").status_code
            == 202
        )
    assert client.get(url(case)).status_code == 409
    assert detail(client, case)["available_actions"] == ["close_case"]


def test_submit_without_personal_data_is_409(client, case, run_tasks):
    create(client, case, run_tasks)
    case.refresh_from_db()
    response = client.post(
        url(case, "/submit"),
        {"expected_version": case.version, "claim_version": 1, "consent": CONSENT},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["details"] == {"fields": ["personal_data"]}


def confirm(client, case):
    case.refresh_from_db()
    return client.put(
        url(case, "/personal-data"),
        {"expected_version": case.version, "data": PERSONAL, "confirmed": True},
        format="json",
    )


def test_submit_rejects_stale_claim_version_and_missing_consent(client, case, run_tasks):
    create(client, case, run_tasks)
    confirm(client, case)
    case.refresh_from_db()
    base = {"expected_version": case.version, "claim_version": 1, "consent": CONSENT}
    assert (
        client.post(url(case, "/submit"), {**base, "claim_version": 2}, format="json").status_code
        == 409
    )
    no_consent = {**base, "consent": {"accepted": False, "text_version": "demo-v1"}}
    assert client.post(url(case, "/submit"), no_consent, format="json").status_code == 400
    forged = {**base, "paid": True}
    assert client.post(url(case, "/submit"), forged, format="json").status_code == 400
    assert client.post(url(case, "/submit"), base, format="json").status_code == 200
    assert client.post(url(case, "/submit"), base, format="json").status_code == 409


def test_create_requires_facts_and_names_them(client, owner, run_tasks):
    case = confirmed_case(
        owner, {k: v for k, v in ANYA_FACTS.items() if k != "amount"}, state="claim_draft"
    )
    response = create(client, case, run_tasks)
    assert response.status_code == 409
    assert response.data["details"] == {"fields": ["amount"]}
    assert not Claim.objects.exists()


def test_create_only_once_and_only_in_claim_draft(client, owner, case, run_tasks):
    assert create(client, case, run_tasks).status_code == 202
    assert create(client, case, run_tasks).status_code == 409
    assert ClaimVersion.objects.count() == 1
    other = confirmed_case(owner)  # card_confirmed, path not chosen
    assert create(client, other, run_tasks).status_code == 409


def test_failed_draft_can_be_retried(client, case, run_tasks):
    with patch.object(tasks, "draft_claim", side_effect=RuntimeError("model down")):
        create(client, case, run_tasks)
    state = detail(client, case)
    assert state["ai_state"] == "failed"
    assert state["available_actions"] == ["create_claim", "close_case"]
    assert create(client, case, run_tasks).status_code == 202
    assert client.get(url(case)).json()["current_version"] == 1


@pytest.mark.parametrize(
    "data",
    [
        {**PERSONAL, "full_name": ""},
        {**PERSONAL, "reply_address": "line\u0000break"},
        {k: v for k, v in PERSONAL.items() if k != "contract_reference"},
        {**PERSONAL, "phone": "+7 900 000-00-00"},
    ],
)
def test_personal_data_validation(client, case, run_tasks, data):
    create(client, case, run_tasks)
    case.refresh_from_db()
    response = client.put(
        url(case, "/personal-data"),
        {"expected_version": case.version, "data": data, "confirmed": True},
        format="json",
    )
    assert response.status_code == 400
    assert not ClaimPersonalData.objects.exists()


def test_personal_data_requires_explicit_confirmation(client, case, run_tasks):
    create(client, case, run_tasks)
    case.refresh_from_db()
    response = client.put(
        url(case, "/personal-data"),
        {"expected_version": case.version, "data": PERSONAL, "confirmed": False},
        format="json",
    )
    assert response.status_code == 400


def test_version_history_keeps_author_and_comment(client, case, run_tasks):
    create(client, case, run_tasks)
    claim = Claim.objects.get()
    lawyer = make_user("lawyer", role="lawyer")
    ClaimVersion.objects.create(
        claim=claim,
        version=2,
        author="lawyer",
        author_user=lawyer,
        template_text="Исправленный текст {{claimant}}",
        comment="Уточнил требование",
    )
    claim.current_version = 2
    claim.save()
    versions = client.get(url(case)).json()["versions"]
    assert [(v["version"], v["author"], v["comment"]) for v in versions] == [
        (1, "ai", None),
        (2, "lawyer", "Уточнил требование"),
    ]


def test_foreign_claim_is_404(client, case, run_tasks):
    create(client, case, run_tasks)
    confirm(client, case)
    case.refresh_from_db()
    for role in ("user", "lawyer"):
        stranger = APIClient()
        stranger.force_login(make_user(f"stranger-{role}", role=role))
        assert stranger.get(url(case)).status_code == 404
        put = stranger.put(
            url(case, "/personal-data"),
            {"expected_version": case.version, "data": PERSONAL, "confirmed": True},
            format="json",
        )
        assert put.status_code == 404
        submit = stranger.post(
            url(case, "/submit"),
            {"expected_version": case.version, "claim_version": 1, "consent": CONSENT},
            format="json",
        )
        assert submit.status_code == 404
