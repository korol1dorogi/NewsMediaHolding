"""S7: no action without consent; every consent point stores a record."""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.cases.models import Case
from apps.cases.tasks import process_message
from apps.cases.testing import make_user
from apps.privacy.models import CONSENT_TEXTS, Consent

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    client = APIClient()
    client.force_login(make_user("owner"))
    return client


def create(client, consent):
    with patch.object(process_message, "delay"):
        return client.post(
            "/api/cases", {"message": "Курс не вернули", "consent": consent}, format="json"
        )


@pytest.mark.parametrize(
    "consent",
    [
        None,
        {},
        {"accepted": False, "text_version": "demo-v1"},
        {"accepted": "true", "text_version": "demo-v1"},
        {"accepted": True, "text_version": "unknown-v9"},
    ],
)
def test_case_needs_consent(client, consent):
    body = {"message": "Курс не вернули"}
    if consent is not None:
        body["consent"] = consent
    with patch.object(process_message, "delay"):
        response = client.post("/api/cases", body, format="json")
    assert response.status_code == 400
    assert not Case.objects.exists()
    assert not Consent.objects.exists()


def test_case_consent_is_recorded(client):
    response = create(client, {"accepted": True, "text_version": "demo-v1"})
    assert response.status_code == 201
    consent = Consent.objects.get()
    assert consent.kind == "processing_offer"
    assert consent.text_version == "demo-v1"
    assert str(consent.case_id) == response.data["id"]


def test_texts_are_marked_as_drafts():
    for texts in CONSENT_TEXTS.values():
        assert set(texts) == set(Consent.Kind.values)
        assert all(text.startswith("ЧЕРНОВИК") for text in texts.values())
