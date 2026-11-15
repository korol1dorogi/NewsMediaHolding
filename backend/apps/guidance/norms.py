"""File-backed legal reference library, never a substitute for legal review."""

import json
from pathlib import Path

_SOURCE = Path(__file__).parent / "resources" / "norms.json"


def select_norms(confirmed_conditions):
    """Return norms only where *all* documented conditions are confirmed.

    Conditions are internal classification evidence supplied by the caller, not
    Case fact keys. An omitted or unknown condition is not a confirmation.
    """
    confirmed = frozenset(confirmed_conditions)
    norms = json.loads(_SOURCE.read_text(encoding="utf-8"))
    return [norm for norm in norms if set(norm["conditions"]) <= confirmed]
