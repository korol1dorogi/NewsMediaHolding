"""Company registry providers. ``mock`` never touches the network."""

import json
import logging
from datetime import UTC, datetime
from urllib import error, request

from django.conf import settings

logger = logging.getLogger(__name__)

DEMO_INN = "0000000000"  # sentinel fixture only, never sent to a real registry
_TIMEOUT_SECONDS = 5


class ProviderUnavailable(Exception):
    """The registry could not answer; the caller records status=unavailable."""


# Mock cache: demo INNs and their registry answers. Tests may extend it.
MOCK_FIXTURES = {
    DEMO_INN: {
        "status": "active",
        "name": "Учебный проект Демо",
        "registered_on": "2020-01-15",
    },
}


def mock_lookup(inn):
    answer = MOCK_FIXTURES.get(inn)
    if answer is None:
        # The mock knows only demo companies; a real INN is not looked up offline.
        raise ProviderUnavailable("Company is not in the mock cache")
    return {**answer, "source": "demo-fixture", "is_demo": inn == DEMO_INN}


_DADATA_STATUS = {
    "ACTIVE": "active",
    "REORGANIZING": "active",
    "LIQUIDATING": "liquidating",
    # No separate enum value: a liquidated company cannot satisfy a claim either.
    "LIQUIDATED": "liquidating",
    "BANKRUPT": "bankrupt",
}


def dadata_lookup(inn):
    """DaData findById/party. Not verified against a live key in the prototype."""
    if inn == DEMO_INN:
        raise ProviderUnavailable("Demo sentinel is not sent to a real registry")
    key = settings.COMPANIES_API_KEY
    if not key:
        raise ProviderUnavailable("COMPANIES_API_KEY is not configured")
    body = json.dumps({"query": inn, "count": 1}).encode()
    url = settings.COMPANIES_API_URL
    if not url.startswith("https://"):
        raise ProviderUnavailable("COMPANIES_API_URL must be https")
    req = request.Request(  # noqa: S310 - https enforced above
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.load(response)
        found = payload["suggestions"]
        if not found:
            raise ProviderUnavailable("Company not found")
        data = found[0]["data"]
        status = _DADATA_STATUS.get(data["state"]["status"])
        if status is None:
            raise ProviderUnavailable("Unknown registry status")
        registered = data["state"].get("registration_date")
        return {
            "status": status,
            "name": found[0].get("value") or None,
            "registered_on": datetime.fromtimestamp(registered / 1000, tz=UTC).date().isoformat()
            if isinstance(registered, int | float)
            else None,
            "source": "dadata",
            "is_demo": False,
        }
    except (OSError, ValueError, KeyError, IndexError, TypeError, error.URLError) as exc:
        logger.warning("Company registry lookup failed: %s", type(exc).__name__)
        raise ProviderUnavailable("Registry request failed") from None


PROVIDERS = {"mock": mock_lookup, "dadata": dadata_lookup}
