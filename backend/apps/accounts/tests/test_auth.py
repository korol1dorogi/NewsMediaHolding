from io import StringIO
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import LawyerProfile

pytestmark = pytest.mark.django_db
PASSWORD = "synthetic-test-password"
LOCAL_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture(autouse=True)
def local_cache():
    with override_settings(CACHES=LOCAL_CACHE, AUTH_LOGIN_ATTEMPTS=10):
        cache.clear()
        yield
        cache.clear()


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="synthetic_user", password=PASSWORD)


@pytest.fixture
def client():
    return APIClient(enforce_csrf_checks=True)


def csrf(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def login(client, username, password=PASSWORD, **headers):
    return client.post(
        "/api/auth/login",
        {"username": username, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
        **headers,
    )


def test_anonymous_login_is_csrf_protected(client, user):
    response = client.post(
        "/api/auth/login", {"username": user.username, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 403
    assert set(response.json()) == {"code", "message", "details"}
    csrf(client)
    assert client.cookies["csrftoken"]["samesite"] == "Lax"
    old_cookie = client.cookies["csrftoken"].value
    bad = client.post(
        "/api/auth/login",
        {"username": user.username, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN="bad-token",
    )
    assert bad.status_code == 403
    assert login(client, user.username).status_code == 200
    assert client.cookies["csrftoken"].value != old_cookie


def test_session_round_trip_and_csrf_logout(client, user):
    csrf(client)
    old_cookie = client.cookies["csrftoken"].value
    response = login(client, user.username)
    assert response.json() == {
        "id": str(user.pk),
        "username": user.username,
        "role": "user",
        "is_demo": False,
    }
    assert client.cookies["sessionid"]["httponly"]
    assert client.cookies["sessionid"]["samesite"] == "Lax"
    assert client.get("/api/auth/me").json() == response.json()
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", HTTP_X_CSRFTOKEN=old_cookie).status_code == 403
    assert client.post("/api/auth/logout", HTTP_X_CSRFTOKEN=csrf(client)).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_unknown_and_inactive_accounts_are_indistinguishable(client, user):
    invalid = login(client, user.username, "wrong-password")
    unknown = login(client, "does_not_exist")
    user.is_active = False
    user.save(update_fields=["is_active"])
    inactive = login(client, user.username)
    assert invalid.status_code == unknown.status_code == inactive.status_code == 401
    assert invalid.json() == unknown.json() == inactive.json()
    assert "password" not in str(invalid.json())


@pytest.mark.parametrize("extra", [{"role": "moderator"}, {"is_superuser": True}, {"owner": "x"}])
def test_login_rejects_privilege_fields(client, user, extra):
    response = client.post(
        "/api/auth/login",
        {"username": user.username, "password": PASSWORD, **extra},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
    )
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.role == "user" and not user.is_superuser


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/auth/logout"])
def test_anonymous_is_401_with_session_challenge(client, path):
    response = client.get(path) if path.endswith("me") else client.post(path)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"
    assert set(response.json()) == {"code", "message", "details"}


@override_settings(ROOT_URLCONF="apps.accounts.tests.urls")
@pytest.mark.parametrize("role", ["user", "lawyer", "moderator", "editor"])
def test_roles_dont_inherit_one_another(client, role):
    account = get_user_model().objects.create_user(username=f"test_{role}", role=role)
    client.force_login(account)
    for target in ["user", "lawyer", "moderator", "editor"]:
        response = client.get(f"/test/{target}")
        assert response.status_code == (200 if role == target else 403)


@override_settings(AUTH_LOGIN_ATTEMPTS=2, AUTH_LOGIN_WINDOW_SECONDS=60)
def test_login_limit_and_no_password_in_logs(client, user, caplog):
    assert login(client, user.username, "wrong-1").status_code == 401
    assert login(client, user.username, "wrong-2").status_code == 401
    response = login(client, user.username)
    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert "wrong-1" not in caplog.text and PASSWORD not in caplog.text


def test_login_fails_closed_if_shared_cache_is_down(client, user, caplog):
    with mock.patch(
        "apps.accounts.throttling.cache.add", side_effect=ConnectionError("secret-cache-url")
    ):
        response = login(client, user.username)
    assert response.status_code == 503
    assert "secret-cache-url" not in str(response.json()) + caplog.text
    assert client.get("/api/auth/me").status_code == 401


@override_settings(AUTH_LOGIN_ATTEMPTS=2, AUTH_TRUST_PROXY_HEADER=True)
def test_two_clients_behind_caddy_have_independent_ip_buckets(client):
    assert login(client, "missing-one", HTTP_X_NMH_CLIENT_IP="192.0.2.1").status_code == 401
    assert login(client, "missing-two", HTTP_X_NMH_CLIENT_IP="192.0.2.1").status_code == 401
    assert login(client, "missing-three", HTTP_X_NMH_CLIENT_IP="192.0.2.2").status_code == 401


@override_settings(AUTH_LOGIN_ATTEMPTS=1, AUTH_TRUST_PROXY_HEADER=False)
def test_untrusted_forwarded_headers_cannot_reset_ip_bucket(client):
    assert login(client, "missing-one", HTTP_X_FORWARDED_FOR="192.0.2.1").status_code == 401
    response = login(
        client, "missing-two", HTTP_X_FORWARDED_FOR="192.0.2.2", HTTP_X_NMH_CLIENT_IP="192.0.2.3"
    )
    assert response.status_code == 429


@override_settings(AUTH_LOGIN_ATTEMPTS=1)
def test_malformed_json_consumes_ip_limit(client):
    first = client.post(
        "/api/auth/login", "{", content_type="application/json", HTTP_X_CSRFTOKEN=csrf(client)
    )
    assert first.status_code == 400
    assert login(client, "missing-next").status_code == 429


@pytest.mark.parametrize("role", ["user", "lawyer", "editor", "moderator"])
def test_admin_requires_moderator_and_staff(client, role):
    account = get_user_model().objects.create_user(
        username=f"admin_{role}", role=role, is_staff=True
    )
    client.force_login(account)
    assert client.get("/admin/").status_code == (200 if role == "moderator" else 302)
    assert client.get("/admin/accounts/user/").status_code in {302, 404}
    assert client.get("/admin/auth/group/").status_code in {302, 404}


def test_nonstaff_or_inactive_moderator_cannot_enter_admin(client):
    account = get_user_model().objects.create_user(username="mod_no_staff", role="moderator")
    client.force_login(account)
    assert client.get("/admin/").status_code == 302
    account.is_staff = True
    account.is_active = False
    account.save()
    assert client.get("/admin/").status_code == 302


def test_seed_is_idempotent_preserves_passwords_roles_and_ratings():
    output = StringIO()
    call_command("seed_demo", stdout=output)
    model = get_user_model()
    assert model.objects.count() == 5
    assert LawyerProfile.objects.count() == 2
    account = model.objects.get(username="demo_anya")
    account.set_password("manually-changed")
    account.role = "editor"
    account.save()
    moderator = model.objects.get(username="demo_moderator")
    assert moderator.is_staff and not moderator.is_superuser
    profile = LawyerProfile.objects.first()
    profile.rating = 42
    profile.save()
    call_command("seed_demo", stdout=output)
    account.refresh_from_db()
    profile.refresh_from_db()
    assert model.objects.count() == 5 and LawyerProfile.objects.count() == 2
    assert account.check_password("manually-changed") and account.role == "editor"
    assert profile.rating == 42
    call_command("seed_demo", reset_passwords=True, stdout=output)
    account.refresh_from_db()
    assert account.check_password("demo-user-placeholder")
    assert "demo-user-placeholder" not in output.getvalue()


def test_seed_refuses_non_demo_collision_atomically():
    get_user_model().objects.create_user(username="demo_editor")
    with pytest.raises(CommandError):
        call_command("seed_demo", stdout=StringIO())
    assert get_user_model().objects.count() == 1


@override_settings(AUTH_LOGIN_ATTEMPTS=2)
def test_normalized_account_limit_survives_different_ips(client, user):
    first = login(client, f" {user.username} ", "bad", REMOTE_ADDR="192.0.2.10")
    second = login(client, user.username, "bad", REMOTE_ADDR="192.0.2.11")
    third = login(client, f"  {user.username}", "bad", REMOTE_ADDR="192.0.2.12")
    assert first.status_code == second.status_code == 401
    assert third.status_code == 429
