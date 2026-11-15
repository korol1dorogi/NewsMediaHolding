"""Verify process-level cookie configuration without mutating Django settings."""

import json
import os
import subprocess
import sys

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("false", False), ("true", True)],
)
def test_secure_cookies_require_explicit_https_mode(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("HTTPS_SECURE_COOKIES", raising=False)
    else:
        monkeypatch.setenv("HTTPS_SECURE_COOKIES", value)
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import json; from config import settings; "
            "print(json.dumps([settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE]))",
        ],
        env=os.environ.copy(),
        text=True,
    )
    assert json.loads(output) == [expected, expected]


@pytest.mark.django_db
@pytest.mark.parametrize("https", [False, True])
def test_auth_sets_cookie_flags_and_enforces_csrf(settings, https):
    settings.SESSION_COOKIE_SECURE = https
    settings.CSRF_COOKIE_SECURE = https
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.AUTH_LOGIN_ATTEMPTS = 10
    get_user_model().objects.create_user(username="cookie_test", password="synthetic-pass")
    client = APIClient(enforce_csrf_checks=True)
    csrf_response = client.get("/api/auth/csrf", secure=https)
    assert csrf_response.status_code == 200
    assert bool(csrf_response.cookies["csrftoken"]["secure"]) is https
    payload = {"username": "cookie_test", "password": "synthetic-pass"}
    assert client.post("/api/auth/login", payload, format="json", secure=https).status_code == 403
    headers = {"HTTP_X_CSRFTOKEN": csrf_response.json()["csrf_token"]}
    if https:
        headers["HTTP_REFERER"] = "https://testserver/api/auth/login"
    response = client.post("/api/auth/login", payload, format="json", secure=https, **headers)
    assert response.status_code == 200
    assert bool(response.cookies["sessionid"]["secure"]) is https
    assert bool(response.cookies["csrftoken"]["secure"]) is https
    assert client.get("/api/auth/me", secure=https).status_code == 200
