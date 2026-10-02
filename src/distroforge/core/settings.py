"""User settings (``~/.config/distroforge/settings.yaml``).

Unknown keys are ignored and invalid values fall back to defaults, so a
hand-edited file can never crash the app.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

import yaml

from distroforge.core.logging import get_logger
from distroforge.core.shellrc import atomic_write
from distroforge.core.validate import ValidationError, check, check_email, check_text

log = get_logger("settings")

DEFAULT_THEME = "catppuccin-mocha"
PREFER_CHOICES = ("native", "flatpak")
SCOPE_CHOICES = ("user", "system")


@dataclass(frozen=True)
class Settings:
    theme: str = DEFAULT_THEME
    prefer: str = "native"  # which install method wins when several are available
    flatpak_scope: str = "user"
    git_name: str = ""
    git_email: str = ""
    skip_installed: bool = True

    def validated(self) -> Settings:
        """Return a copy with every invalid field reset to its default."""
        defaults = Settings()
        clean: dict[str, Any] = {}
        validators: dict[str, Callable[[Any], Any]] = {
            "theme": lambda v: check("theme", v),
            "prefer": lambda v: _choice(v, PREFER_CHOICES),
            "flatpak_scope": lambda v: _choice(v, SCOPE_CHOICES),
            "git_name": _git_name,
            "git_email": lambda v: v if v == "" else check_email(v),
            "skip_installed": lambda v: _bool(v),
        }
        for f in fields(self):
            value = getattr(self, f.name)
            try:
                clean[f.name] = validators[f.name](value)
            except ValidationError as exc:
                log.warning("Ignoring invalid setting %s: %s", f.name, exc)
                clean[f.name] = getattr(defaults, f.name)
        return replace(self, **clean)


def _choice(value: object, choices: tuple[str, ...]) -> str:
    if value not in choices:
        raise ValidationError(f"Expected one of {choices}, got {value!r}")
    return str(value)


def _git_name(value: object) -> str:
    name = check_text(value, max_len=100, field="git name")
    if name.startswith("-"):
        raise ValidationError("git name must not start with '-'")
    return name


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"Expected true/false, got {value!r}")
    return value


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.warning("Could not read %s: %s", path, exc)
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in data.items() if k in known}).validated()


def save_settings(path: Path, settings: Settings) -> None:
    content = yaml.safe_dump(asdict(settings.validated()), sort_keys=False)
    atomic_write(path, "# DistroForge settings — edited from the Settings screen\n" + content)
    path.chmod(0o600)
