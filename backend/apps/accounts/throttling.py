import hashlib
import hmac
import ipaddress

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import APIException, Throttled


class AuthUnavailable(APIException):
    status_code = 503
    default_detail = "Вход временно недоступен."


def _increment(key, window):
    """RedisCache add/incr are atomic across Gunicorn workers; retry an expired key."""
    for _ in range(2):
        if cache.add(key, 1, timeout=window):
            return 1
        try:
            return cache.incr(key)
        except ValueError:
            continue
    raise AuthUnavailable


def _enforce(kind, identity):
    window = max(1, settings.AUTH_LOGIN_WINDOW_SECONDS)
    try:
        digest = hmac.new(
            settings.SECRET_KEY.encode(), identity.encode(), hashlib.sha256
        ).hexdigest()
        count = _increment(f"login:{kind}:{digest}", window)
    except AuthUnavailable:
        raise
    except Exception:
        raise AuthUnavailable from None
    if count > max(1, settings.AUTH_LOGIN_ATTEMPTS):
        raise Throttled(wait=window)


def enforce_login_ip_limit(request):
    # Opt-in only behind the bundled Caddy ingress, which overwrites this header.
    # Backend has no published ports; arbitrary X-Forwarded-For is never trusted.
    remote = request.META.get("REMOTE_ADDR", "unknown")
    candidate = request.META.get("HTTP_X_NMH_CLIENT_IP", remote)
    if settings.AUTH_TRUST_PROXY_HEADER:
        try:
            remote = str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    _enforce("ip", remote)


def enforce_login_account_limit(username):
    _enforce("account", username.casefold())
