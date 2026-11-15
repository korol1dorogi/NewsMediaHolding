"""A7: PDF documents are accepted only when inert and are never rendered."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.cases.models import Case
from apps.cases.testing import make_user

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n%%EOF"


@pytest.fixture
def setup():
    owner = make_user("owner")
    case = Case.objects.create(owner=owner, ai_state="idle", consent_text_version="v1")
    client = APIClient()
    client.force_login(owner)
    return client, case


def upload(client, case, name, content, mime="application/pdf"):
    case.refresh_from_db()
    return client.post(
        f"/api/cases/{case.pk}/documents",
        {
            "file": SimpleUploadedFile(name, content, content_type=mime),
            "expected_version": case.version,
        },
        format="multipart",
    )


def test_inert_pdf_is_accepted_and_served_as_attachment(setup):
    client, case = setup
    response = upload(client, case, "договор.pdf", PDF)
    assert response.status_code == 201, response.data
    assert response.data["content_type"] == "application/pdf"
    download = client.get(f"/api/cases/{case.pk}/documents/{response.data['id']}/content")
    assert download["Content-Type"] == "application/pdf"
    assert download["Content-Disposition"].startswith("attachment")
    assert "sandbox" in download["Content-Security-Policy"]


@pytest.mark.parametrize(
    "marker",
    [
        b"/JavaScript",
        b"/JS (app.alert(1))",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
        b"/AA",
        b"/XFA",
    ],
)
def test_active_pdf_is_rejected(setup, marker):
    client, case = setup
    response = upload(client, case, "evil.pdf", PDF.replace(b">> endobj", marker + b" >> endobj"))
    assert response.status_code == 400
    assert not case.documents.exists()


@pytest.mark.parametrize(
    ("name", "content", "mime"),
    [
        ("fake.pdf", b"<html>not a pdf</html>", "application/pdf"),
        ("doc.pdf", PDF, "text/plain"),
    ],
)
def test_spoofed_pdf_is_rejected(setup, name, content, mime):
    client, case = setup
    assert upload(client, case, name, content, mime).status_code == 400


def test_names_like_js_inside_text_are_not_active_content(setup):
    client, case = setup
    content = PDF.replace(b"/Catalog", b"/Catalog /JSON-like-name-is-fine /AAA")
    assert upload(client, case, "ok.pdf", content).status_code == 201
