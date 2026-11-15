"""S5: personal data access leaves a record that nobody can change through the admin."""

import pytest
from django.test import Client

from apps.audit.models import AccessLog, log_access
from apps.cases.testing import confirmed_case, make_user
from apps.claims.models import Claim

pytestmark = pytest.mark.django_db


@pytest.fixture
def moderator():
    user = make_user("moderator", role="moderator")
    user.is_staff = True
    user.save()
    return user


def test_moderator_view_is_logged(moderator):
    case = confirmed_case(make_user("owner"), state="claim_draft")
    claim = Claim.objects.create(case=case, card_version=1)
    client = Client()
    client.force_login(moderator)
    response = client.get(f"/admin/claims/claim/{claim.pk}/change/")
    assert response.status_code == 200
    entry = AccessLog.objects.get()
    assert entry.basis == "moderation" and entry.actor == moderator
    assert entry.target_id == claim.pk and entry.case_id == case.pk


def test_log_is_read_only_in_admin(moderator):
    entry = log_access(
        make_user("lawyer", role="lawyer"), "claim", moderator.pk, "review_assignment"
    )
    client = Client()
    client.force_login(moderator)
    base = "/admin/audit/accesslog/"
    assert client.get(base).status_code == 200
    assert client.get(f"{base}{entry.pk}/change/").status_code == 200
    assert client.get(f"{base}add/").status_code == 403
    assert client.post(f"{base}{entry.pk}/delete/", {"post": "yes"}).status_code == 403
    assert (
        client.post(
            f"{base}{entry.pk}/change/", {"role": "editor", "basis": "moderation"}
        ).status_code
        == 403
    )
    entry.refresh_from_db()
    assert entry.role == "lawyer"
    assert AccessLog.objects.count() == 1


@pytest.mark.parametrize("role", ["user", "lawyer", "editor"])
def test_other_roles_cannot_open_admin(role):
    user = make_user(f"x-{role}", role=role)
    user.is_staff = True
    user.save()
    client = Client()
    client.force_login(user)
    response = client.get("/admin/audit/accesslog/")
    assert response.status_code == 302  # back to the admin login


def test_log_has_no_personal_values():
    fields = {field.name for field in AccessLog._meta.get_fields()}
    assert fields == {
        "id",
        "actor",
        "role",
        "target_type",
        "target_id",
        "case_id",
        "basis",
        "created_at",
    }
