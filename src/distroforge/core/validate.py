"""Input validation shared by the catalog, actions and settings.

Commands never pass through a shell, so the remaining injection vector is
*option injection* (a value such as ``--config=/evil`` being read as a flag).
Every identifier is therefore matched against a strict allow-list pattern that
cannot start with ``-``.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit


class ValidationError(ValueError):
    """Raised when user- or catalog-supplied data is unsafe or malformed."""


PATTERNS: dict[str, re.Pattern[str]] = {
    "id": re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$"),
    "package": re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._@:-]{0,127}$"),
    "flatpak": re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+){2,}$"),
    "unit": re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._:-]{0,127}$"),
    "group": re.compile(r"^[a-z_][a-z0-9_-]{0,31}$"),
    "sysctl_key": re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$"),
    "sysctl_value": re.compile(r"^[0-9]{1,10}( [0-9]{1,10}){0,3}$"),
    "module": re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}$"),
    "repo_name": re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$"),
    "keyring": re.compile(r"^[a-z0-9][a-z0-9-]{0,63}\.(asc|gpg)$"),
    "apt_token": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$"),
    "font": re.compile(r"^[A-Za-z0-9]{1,64}$"),
    "env_key": re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$"),
    "binary": re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]{0,63}$"),
    "shell": re.compile(r"^(bash|zsh|fish)$"),
    "theme": re.compile(r"^[a-z0-9-]{1,64}$"),
}


def check(kind: str, value: object) -> str:
    """Return ``value`` if it matches the ``kind`` pattern, else raise."""
    if not isinstance(value, str) or not PATTERNS[kind].match(value):
        raise ValidationError(f"Invalid {kind.replace('_', ' ')}: {value!r}")
    return value


def check_https_url(value: object, *, allow_vars: bool = False) -> str:
    """Require an absolute https URL without whitespace or credentials.

    ``allow_vars`` permits dnf's ``$releasever``/``$basearch`` placeholders.
    """
    if not isinstance(value, str) or any(ch.isspace() for ch in value) or len(value) > 512:
        raise ValidationError(f"Invalid URL: {value!r}")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValidationError(f"Only plain https:// URLs are allowed: {value!r}")
    if "$" in value and not allow_vars:
        raise ValidationError(f"Variables are not allowed in this URL: {value!r}")
    if any(ch in value for ch in "\"'`\\<>"):
        raise ValidationError(f"Invalid characters in URL: {value!r}")
    return value


def check_text(value: object, *, max_len: int = 200, field: str = "text") -> str:
    """Free text for display or config values (git name, comments)."""
    if not isinstance(value, str) or len(value) > max_len:
        raise ValidationError(f"Invalid {field}: {value!r}")
    if any(ord(ch) < 32 for ch in value):
        raise ValidationError(f"Control characters are not allowed in {field}")
    return value


def check_email(value: object) -> str:
    text = check_text(value, max_len=254, field="email")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text):
        raise ValidationError(f"Invalid email: {value!r}")
    return text


def check_path_within(value: str, roots: tuple[str, ...]) -> str:
    """Require an absolute, normalised path inside one of ``roots``."""
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValidationError(f"Unsafe path: {value!r}")
    if not any(path.is_relative_to(root) and path != PurePosixPath(root) for root in roots):
        raise ValidationError(f"Path {value!r} is outside the allowed locations")
    return value
