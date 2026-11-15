"""S4: uploads are checked by content, bounded, and served only as attachments to the owner."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.cases.models import Case
from apps.cases.testing import make_user
from apps.cases.views import safe_filename

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


@pytest.fixture
def owner():
    return make_user("owner")


@pytest.fixture
def case(owner):
    return Case.objects.create(owner=owner, ai_state="idle", consent_text_version="v1")


@pytest.fixture
def client(owner):
    client = APIClient()
    client.force_login(owner)
    return client


def upload(client, case, name, content, mime):
    case.refresh_from_db()
    return client.post(
        f"/api/cases/{case.pk}/documents",
        {
            "file": SimpleUploadedFile(name, content, content_type=mime),
            "expected_version": case.version,
        },
        format="multipart",
    )


@pytest.mark.parametrize(
    ("name", "content", "mime"),
    [
        ("receipt.png", PNG, "image/png"),
        ("receipt.jpeg", JPEG, "image/jpeg"),
        ("note.txt", "Чек на 68 000 ₽".encode(), "text/plain"),
    ],
)
def test_allowed_types(client, case, name, content, mime):
    response = upload(client, case, name, content, mime)
    assert response.status_code == 201, response.data
    assert response.data["content_type"] == mime


@pytest.mark.parametrize(
    ("name", "content", "mime"),
    [
        # Wrong type altogether.
        ("page.html", b"<script>alert(1)</script>", "text/html"),
        # PDF itself is allowed since A7 (see test_pdf.py); a fake one is not.
        ("doc.pdf", b"<html>not a pdf</html>", "application/pdf"),
        # Extension spoofing: content does not match the extension.
        ("photo.png", b"<svg onload=alert(1)>", "image/png"),
        ("photo.jpg", PNG, "image/jpeg"),
        ("note.txt", PNG, "text/plain"),
        # Declared type does not match the content.
        ("photo.png", PNG, "image/jpeg"),
        # Text that is not UTF-8.
        ("note.txt", "Чек".encode("cp1251"), "text/plain"),
        # Empty file.
        ("note.txt", b"", "text/plain"),
    ],
)
def test_rejected_files(client, case, name, content, mime):
    response = upload(client, case, name, content, mime)
    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert not case.documents.exists()


def test_size_limit(client, case, settings):
    settings.DOCUMENTS_MAX_BYTES = 10
    response = upload(client, case, "note.txt", b"x" * 11, "text/plain")
    assert response.status_code == 400
    assert response.data["details"]["file"] == ["Файл слишком большой."]
    assert upload(client, case, "note.txt", b"x" * 10, "text/plain").status_code == 201


def test_file_count_limit(client, case, settings):
    settings.DOCUMENTS_MAX_PER_CASE = 2
    for _ in range(2):
        assert upload(client, case, "note.txt", b"ok", "text/plain").status_code == 201
    response = upload(client, case, "note.txt", b"ok", "text/plain")
    assert response.status_code == 400
    assert case.documents.count() == 2


@pytest.mark.parametrize(
    ("name", "mime", "expected"),
    [
        ("../../etc/passwd.txt", "text/plain", "passwd.txt"),
        ("C:\\Users\\anya\\чек.png", "image/png", "чек.png"),
        ('evil"\r\nX-Header: 1.txt', "text/plain", "evil_X-Header_ 1.txt"),
        ("noext", "image/jpeg", "noext.jpg"),
        ("...", "text/plain", "document.txt"),
        ("a" * 300 + ".png", "image/png", "a" * 100 + ".png"),
    ],
)
def test_safe_filename(name, mime, expected):
    assert safe_filename(name, mime) == expected


def test_download_is_attachment_without_rendering(client, case):
    doc = upload(client, case, "../x.txt", b"demo", "text/plain").data
    response = client.get(f"/api/cases/{case.pk}/documents/{doc['id']}/content")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    assert 'filename="x.txt"' in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response["Content-Security-Policy"]
    assert response["Cache-Control"] == "private, no-store"


def test_foreign_file_is_404_and_no_direct_url_exists(client, case):
    doc = upload(client, case, "x.txt", b"demo", "text/plain").data
    assert "url" not in doc and "path" not in doc
    stranger = APIClient()
    stranger.force_login(make_user("stranger"))
    assert stranger.get(f"/api/cases/{case.pk}/documents/{doc['id']}/content").status_code == 404
    lawyer = APIClient()
    lawyer.force_login(make_user("lawyer", role="lawyer"))
    assert lawyer.get(f"/api/cases/{case.pk}/documents/{doc['id']}/content").status_code == 404
