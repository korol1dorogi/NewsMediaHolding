from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from apps.cases.models import Case, Document
from apps.cases.states import Conflict, transition
from apps.cases.tasks import process_message

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner")


@pytest.fixture
def client(owner):
    client = APIClient()
    client.force_login(owner)
    return client


@pytest.fixture
def case(owner):
    return Case.objects.create(owner=owner, consent_text_version="demo-v1", ai_state="idle")


def create(client):
    return client.post(
        "/api/cases",
        {
            "message": "Оплатил тестовый курс.",
            "consent": {"accepted": True, "text_version": "demo-v1"},
        },
        format="json",
    )


def upload(client, case):
    file = SimpleUploadedFile("demo.txt", b"demo", content_type="text/plain")
    return client.post(
        f"/api/cases/{case.pk}/documents",
        {"expected_version": case.version, "file": file},
        format="multipart",
    )


def test_dialog(client, django_capture_on_commit_callbacks):
    with patch.object(process_message, "delay", side_effect=process_message.run) as worker:
        with django_capture_on_commit_callbacks(execute=True):
            created = create(client)
            assert created.status_code == 201
            assert created.data["ai_state"] == "thinking"
            worker.assert_not_called()
        path = "/api/cases/" + created.data["id"]
        case = client.get(path).json()
        assert case["state"] == "clarifying"
        assert case["ai_state"] == "idle"
        assert case["pool"] is None and case["work"] is None
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                path + "/messages",
                {"text": "Вчера.", "expected_version": case["version"]},
                format="json",
            )
            assert response.status_code == 202
            assert response.data["case"]["ai_state"] == "thinking"
        assert client.get(path).data["state"] == "card_ready"
        messages = client.get(path + "/messages").data["items"]
        assert [item["author"] for item in messages] == ["user", "ai", "user", "ai"]
        process_message.run(*worker.call_args.args)
        assert len(client.get(path + "/messages").data["items"]) == 4


@pytest.mark.parametrize("failure", ["provider", "broker"])
def test_failure_allows_new_message(client, django_capture_on_commit_callbacks, failure):
    with (
        patch.object(
            process_message,
            "delay",
            side_effect=(OperationalError() if failure == "broker" else process_message.run),
        ),
        patch("apps.cases.intake.next_step", side_effect=RuntimeError()),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            created = create(client)
    assert created.status_code == 201
    case = Case.objects.get(pk=created.data["id"])
    assert case.ai_state == "failed"
    with patch.object(process_message, "delay", side_effect=process_message.run):
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                f"/api/cases/{case.pk}/messages",
                {"expected_version": case.version, "text": "Ещё раз."},
                format="json",
            )
    assert response.status_code == 202
    case.refresh_from_db()
    assert case.ai_state == "idle"
    assert case.messages.filter(author="user").count() == 2


def test_foreign_data(client, case, django_user_model):
    doc = Document.objects.create(
        case=case, filename="a.txt", size_bytes=1, content_type="text/plain", content=b"a"
    )
    outsider = django_user_model.objects.create_user(username="outsider")
    client.force_login(outsider)
    assert client.get("/api/cases").data == {"items": []}
    path = f"/api/cases/{case.pk}"
    assert client.get(path).status_code == 404
    assert client.get(path + "/messages").status_code == 404
    assert client.post(path + "/messages", {}, format="json").status_code == 404
    assert client.post(path + "/close", {}, format="json").status_code == 404
    assert upload(client, case).status_code == 404
    own = Case.objects.create(owner=outsider, consent_text_version="v1")
    for parent in (own, case):
        response = client.get(f"/api/cases/{parent.pk}/documents/{doc.pk}/content")
        assert response.status_code == 404


def test_document(client, case):
    response = upload(client, case)
    assert response.status_code == 201
    assert response.data["size_bytes"] == 4
    assert "content" not in response.data
    url = f"/api/cases/{case.pk}/documents/{response.data['id']}/content"
    download = client.get(url, HTTP_ACCEPT="text/plain")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == b"demo"
    assert download["Content-Disposition"].startswith("attachment")
    assert download["X-Content-Type-Options"] == "nosniff"
    assert download["Cache-Control"] == "private, no-store"
    assert upload(client, case).status_code == 409
    case.refresh_from_db()
    case.state = "card_confirmed"
    case.save()
    assert upload(client, case).status_code == 409
    assert case.documents.count() == 1


def test_stale_worker_cannot_reopen_closed_case(client):
    created = create(client)
    path = "/api/cases/" + created.data["id"]
    assert (
        client.post(
            path + "/messages", {"text": "ещё", "expected_version": 1}, format="json"
        ).status_code
        == 409
    )
    payload = {"reason": "Решено", "expected_version": 1}
    assert client.post(path + "/close", payload, format="json").status_code == 200
    process_message.run(created.data["id"], 1)
    assert client.get(path).data["state"] == "closed"
    assert len(client.get(path + "/messages").data["items"]) == 1
    assert client.post(path + "/close", payload, format="json").status_code == 409


def test_transitions(case):
    transition(case, "clarifying")
    transition(case, "draft")
    transition(case, "card_ready")
    transition(case, "card_confirmed")
    with pytest.raises(Conflict):
        transition(case, "draft")


@pytest.mark.parametrize(
    "extra",
    [
        {"owner": 2},
        {"state": "closed"},
        {"consent": {"accepted": "true", "text_version": "v1"}},
        {"consent": {"accepted": False, "text_version": "v1"}},
    ],
)
def test_create_rejects_invalid_input(client, extra):
    response = client.post(
        "/api/cases",
        {"message": "Тест", "consent": {"text_version": "v1", "accepted": True}, **extra},
        format="json",
    )
    assert response.status_code == 400
    assert not Case.objects.exists()


def test_session_and_csrf(owner):
    client = APIClient(enforce_csrf_checks=True)
    assert client.get("/api/cases").status_code == 401
    client.force_login(owner)
    assert create(client).status_code == 403
    assert not Case.objects.exists()
