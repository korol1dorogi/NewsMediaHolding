import logging

import redis
from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Liveness: the process is up. Does not touch dependencies."""
    return Response({"status": "ok"})


def _check_db() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("Readiness: database check failed")
        return False


def _check_redis() -> bool:
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception:
        logger.exception("Readiness: redis check failed")
        return False


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def ready(request: Request) -> Response:
    """Readiness: the app can serve traffic (database and redis reachable)."""
    checks = {"database": _check_db(), "redis": _check_redis()}
    is_ready = all(checks.values())
    return Response(
        {"status": "ready" if is_ready else "not_ready", "checks": checks},
        status=200 if is_ready else 503,
    )
