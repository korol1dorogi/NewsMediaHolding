from unittest import mock

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_health_ok(client: APIClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_when_dependencies_up(client: APIClient) -> None:
    with mock.patch("apps.core.views._check_redis", return_value=True):
        response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "redis": True}


@pytest.mark.django_db
def test_not_ready_when_redis_down(client: APIClient) -> None:
    with mock.patch("apps.core.views._check_redis", return_value=False):
        response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_unknown_api_route_is_404(client: APIClient) -> None:
    assert client.get("/api/does-not-exist").status_code == 404
