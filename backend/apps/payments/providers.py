"""Payment providers. Only the demo provider exists: it moves no money."""

import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DemoProvider:
    """Confirms every operation instantly. Shown in the UI as «оплата — демонстрация»."""

    name = "demo"

    def capture(self, amount_kopecks: int) -> str:
        return f"demo-{uuid.uuid4()}"

    def payout(self, provider_reference: str, amount_kopecks: int) -> None:
        return None

    def refund(self, provider_reference: str, amount_kopecks: int) -> None:
        return None


_PROVIDERS = {DemoProvider.name: DemoProvider}


def get_provider() -> DemoProvider:
    name = settings.PAYMENTS_PROVIDER
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ImproperlyConfigured(f"Unknown PAYMENTS_PROVIDER: {name}") from None
