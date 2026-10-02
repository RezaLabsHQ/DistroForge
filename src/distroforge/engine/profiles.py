"""Profiles: named, shareable selections.

Built-in profiles are only *starting points*: loading one fills the selection,
which the user can then change freely. User profiles live in
``~/.config/distroforge/profiles/*.yaml`` and can be copied between machines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from distroforge.backends import BACKEND_NAMES
from distroforge.catalog.models import Catalog
from distroforge.core.logging import get_logger
from distroforge.core.shellrc import atomic_write
from distroforge.core.validate import ValidationError, check, check_text

log = get_logger("profiles")

_METHOD_NAMES = BACKEND_NAMES | {"script"}


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str = ""
    items: tuple[str, ...] = ()
    methods: dict[str, str] = field(default_factory=dict)
    path: Path | None = None  # None for built-ins

    @property
    def builtin(self) -> bool:
        return self.path is None

    def selection(self, catalog: Catalog) -> tuple[dict[str, str | None], list[str]]:
        """Return the selection restricted to known items, and the unknown ids."""
        known = {i: self.methods.get(i) for i in self.items if i in catalog.items}
        unknown = [i for i in self.items if i not in catalog.items]
        return known, unknown


def parse_profile(data: Any, *, fallback_id: str, path: Path | None) -> Profile:
    if not isinstance(data, dict):
        raise ValidationError("profile must be a mapping")
    items = data.get("items") or []
    methods = data.get("methods") or {}
    if not isinstance(items, list) or not isinstance(methods, dict):
        raise ValidationError("'items' must be a list and 'methods' a mapping")
    for item_id, method in methods.items():
        check("id", item_id)
        if method not in _METHOD_NAMES:
            raise ValidationError(f"methods.{item_id}: unknown method {method!r}")
    return Profile(
        id=check("id", data.get("id", fallback_id)),
        name=check_text(data.get("name", fallback_id), max_len=60, field="profile name"),
        description=check_text(data.get("description", ""), max_len=200, field="description"),
        items=tuple(dict.fromkeys(check("id", i) for i in items)),
        methods=dict(methods),
        path=path,
    )


def builtin_profiles() -> list[Profile]:
    root = resources.files("distroforge.catalog") / "data" / "profiles"
    profiles = []
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".yaml"):
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            profiles.append(parse_profile(data, fallback_id=entry.name[:-5], path=None))
    return profiles


def user_profiles(directory: Path) -> list[Profile]:
    profiles = []
    for path in sorted(directory.glob("*.yaml")) if directory.is_dir() else []:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            profiles.append(parse_profile(data, fallback_id=path.stem, path=path))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            log.warning("Skipping profile %s: %s", path, exc)
    return profiles


def load_profiles(directory: Path) -> list[Profile]:
    return builtin_profiles() + user_profiles(directory)


def load_profile_file(path: Path) -> Profile:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_profile(data, fallback_id=slugify(path.stem), path=path)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]
    return slug or "profile"


def save_profile(
    directory: Path,
    name: str,
    selection: dict[str, str | None],
    *,
    description: str = "",
) -> Path:
    profile_id = slugify(check_text(name, max_len=60, field="profile name"))
    data: dict[str, Any] = {
        "id": profile_id,
        "name": name,
        "description": check_text(description, max_len=200, field="description"),
        "items": sorted(selection),
    }
    methods = {k: v for k, v in sorted(selection.items()) if v}
    if methods:
        data["methods"] = methods
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile_id}.yaml"
    atomic_write(
        path,
        "# DistroForge profile — share it, edit it, load it on another machine\n"
        + yaml.safe_dump(data, sort_keys=False),
    )
    return path


def delete_profile(profile: Profile) -> None:
    if profile.path is None:
        raise ValueError("Built-in profiles cannot be deleted")
    profile.path.unlink(missing_ok=True)
