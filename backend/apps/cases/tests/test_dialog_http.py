import json
import time
from urllib.request import Request, urlopen

import pytest
from celery import Celery
from celery.contrib.testing.app import setup_default_app
from celery.contrib.testing.worker import start_worker
from django.conf import settings
from django.middleware.csrf import get_token
from django.test import RequestFactory

from apps.cases.tasks import process_message


@pytest.mark.django_db(transaction=True)
def test_http_dialog_with_worker(live_server, client, django_user_model):
    owner = django_user_model.objects.create_user(username="demo-http")
    client.force_login(owner)
    csrf_request = RequestFactory().get("/")
    csrf = get_token(csrf_request)
    cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"{settings.SESSION_COOKIE_NAME}={cookie}; csrftoken={csrf}",
        "X-CSRFToken": csrf,
    }

    def http(path, body=None, method=None):
        data = None if body is None else json.dumps(body).encode()
        with urlopen(
            Request(live_server.url + path, data, headers, method=method), timeout=5
        ) as reply:
            return reply.status, json.load(reply)

    def poll(path):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            _, detail = http(path)
            if detail["ai_state"] != "thinking":
                return detail
            time.sleep(0.05)
        pytest.fail("Worker did not finish the intake")

    # Run the production task in a worker thread, using an isolated in-memory broker in CI.
    test_app = Celery("b1-http", broker="memory://", set_as_current=False)
    test_app.conf.task_ignore_result = True
    with setup_default_app(test_app):
        test_app.set_current()
        with start_worker(test_app, perform_ping_check=False):
            assert process_message.app is test_app
            status, created = http(
                "/api/cases",
                {
                    "message": "Тестовый курс, Учебный проект Демо",
                    "consent": {"accepted": True, "text_version": "demo-v1"},
                },
            )
            assert status == 201
            path = "/api/cases/" + created["id"]
            first = poll(path)
            assert first["state"] == "clarifying"
            status, _ = http(
                path + "/messages", {"expected_version": first["version"], "text": "Вчера"}
            )
            assert status == 202
            case = poll(path)
            assert case["state"] == "card_ready"
            _, card = http(path + "/card")
            assert card["missing_required_fields"] == ["payment_date"]
            assert card["facts"][0]["source_quote"] == "Учебный проект Демо"
            status, edited = http(
                path + "/card/facts/payment_date",
                {"value": "2 октября", "expected_version": case["version"]},
                "PATCH",
            )
            assert status == 200 and edited["missing_required_fields"] == []
            _, case = http(path)
            status, confirmed = http(
                path + "/card/confirm",
                {"expected_version": case["version"], "card_version": edited["version"]},
            )
            assert status == 200 and confirmed["state"] == "card_confirmed"
            assert http(path + "/card")[1]["facts"] == edited["facts"]
            _, messages = http(path + "/messages")
            assert [item["author"] for item in messages["items"]] == ["user", "ai", "user", "ai"]
