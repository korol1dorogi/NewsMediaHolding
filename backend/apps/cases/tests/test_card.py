from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.cases.models import CardSnapshot, Case, Document, Fact, Message
from apps.cases.tasks import process_message

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(django_user_model):
    owner = django_user_model.objects.create_user(username="owner")
    case = Case.objects.create(
        owner=owner, state="card_ready", ai_state="idle", consent_text_version="v1"
    )
    Fact.objects.create(case=case, key="company_name", required=True)
    return case


@pytest.fixture
def client(case):
    client = APIClient()
    client.force_login(case.owner)
    return client


def test_confirm_guards(client, case):
    base = f"/api/cases/{case.pk}/card"
    versions = {"expected_version": 1, "card_version": 1}
    response = client.post(base + "/confirm", versions, format="json")
    assert response.status_code == 409
    assert response.data["details"]["fields"] == ["company_name"]
    edit = base + "/facts/company_name"
    payload = {"value": "Демо", "expected_version": 1}
    assert client.patch(edit, {**payload, "source_quote": "fake"}, format="json").status_code == 400
    assert client.patch(edit, payload, format="json").data["facts"][0]["status"] == "user_edited"
    assert client.patch(edit, payload, format="json").status_code == 409
    for field in versions:
        stale = dict.fromkeys(versions, 2)
        stale[field] = 1
        response = client.post(base + "/confirm", stale, format="json")
        assert response.status_code == 409 and response.data["details"]["fields"] == [field]
        assert not CardSnapshot.objects.exists()
    response = client.post(base + "/confirm", dict.fromkeys(versions, 2), format="json")
    assert response.status_code == 200
    assert response.data["available_actions"] == ["choose_path", "close_case"]
    before = client.get(base).json()
    assert before["confirmed_at"] and before["version"] == 2
    assert client.patch(edit, {**payload, "expected_version": 3}, format="json").status_code == 409
    assert client.post(base + "/confirm", versions, format="json").status_code == 409
    case.facts.update(value="changed live row")
    assert client.get(base).json() == before


def test_foreign_card(client, case, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="other"))
    base = f"/api/cases/{case.pk}/card"
    assert client.get(base).status_code == 404
    assert client.patch(base + "/facts/company_name", {}, format="json").status_code == 404
    assert client.post(base + "/confirm", {}, format="json").status_code == 404


def test_sources_scoped_to_case_and_checked_verbatim(case):
    case.state = "draft"
    case.ai_state = "thinking"
    case.save()
    foreign = Case.objects.create(owner=case.owner, consent_text_version="v1")
    message = Message.objects.create(case=foreign, author="user", text="Демо")
    doc = Document.objects.create(
        case=case,
        filename="demo.txt",
        content_type="text/plain",
        size_bytes=8,
        content="Демо".encode(),
    )

    def proposal(key, kind, pk, version=1, quote="Демо"):
        return {
            "key": key,
            "status": "found",
            "required": True,
            "value": "Демо",
            "source": {"kind": kind, "id": str(pk), "source_version": version},
            "source_quote": quote,
        }

    proposals = [
        proposal("foreign", "message", message.pk),
        proposal("valid", "document", doc.pk),
        proposal("wrong_quote", "document", doc.pk, quote="Другое"),
        proposal("stale", "document", doc.pk, version=2),
    ]
    with patch(
        "apps.cases.intake.next_step",
        return_value={
            "card_ready": True,
            "urgent": False,
            "missing_documents": [],
            "proposed_facts": proposals,
        },
    ):
        process_message.run(str(case.pk), case.version)
    valid = case.facts.get(key="valid")
    assert valid.source == proposals[1]["source"] and valid.source_quote == "Демо"
    for fact in case.facts.exclude(key="valid"):
        assert fact.status == "not_found" and fact.source is None and not fact.value
