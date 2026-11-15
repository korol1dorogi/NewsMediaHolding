"""INN checksum (ФНС algorithm). Validation only, no lookup."""

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _digit(digits, weights):
    return sum(d * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def normalize_inn(value):
    """Return the INN if its length and checksum are valid, otherwise None."""
    if not isinstance(value, str):
        return None
    text = "".join(value.split())
    if not text.isascii() or not text.isdigit() or len(text) not in (10, 12):
        return None
    digits = [int(ch) for ch in text]
    if len(digits) == 10:
        ok = digits[9] == _digit(digits, _W10)
    else:
        ok = digits[10] == _digit(digits, _W11) and digits[11] == _digit(digits, _W12)
    return text if ok else None
