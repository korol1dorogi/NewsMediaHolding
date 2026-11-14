"""Environment helpers: an empty or missing variable always falls back to a default."""

import os


def env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]
