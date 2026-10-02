"""Load the built-in catalog, then layer the user's ``catalog.d`` on top.

User files can add items, replace built-in items (same ``id``), add categories,
and hide items (``hide: [id, ...]``). Invalid entries are reported and skipped,
never fatal.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from distroforge.catalog.models import Catalog, Category, Item, parse_category, parse_item
from distroforge.core.logging import get_logger
from distroforge.core.validate import ValidationError, check

log = get_logger("catalog")

MAX_FILE_BYTES = 1024 * 1024


def _builtin_files() -> list[tuple[str, str]]:
    data = resources.files("distroforge.catalog") / "data"
    return sorted(
        (entry.name, entry.read_text(encoding="utf-8"))
        for entry in data.iterdir()
        if entry.name.endswith(".yaml")
    )


def _user_files(directory: Path | None) -> list[tuple[str, str]]:
    if directory is None or not directory.is_dir():
        return []
    files = []
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                log.warning("Skipping %s: larger than 1 MiB", path)
                continue
            files.append((str(path), path.read_text(encoding="utf-8")))
        except OSError as exc:
            log.warning("Cannot read %s: %s", path, exc)
    return files


def _load_yaml(name: str, text: str, errors: list[str]) -> dict[str, Any]:
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{name}: invalid YAML: {exc}")
        return {}
    if not isinstance(doc, dict):
        errors.append(f"{name}: top level must be a mapping")
        return {}
    unknown = set(doc) - {"categories", "items", "hide"}
    if unknown:
        errors.append(f"{name}: unknown top-level key(s) {sorted(unknown)}")
    clean: dict[str, Any] = {}
    for key in ("categories", "items", "hide"):
        value = doc.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{name}: '{key}' must be a list")
            continue
        clean[key] = value
    return clean


def load_catalog(user_dir: Path | None = None) -> Catalog:
    errors: list[str] = []
    categories: dict[str, Category] = {}
    items: dict[str, Item] = {}
    hidden: set[str] = set()

    sources = [(name, text, "built-in") for name, text in _builtin_files()]
    sources += [(name, text, f"user: {Path(name).name}") for name, text in _user_files(user_dir)]
    docs = [(name, _load_yaml(name, text, errors), label) for name, text, label in sources]

    # Categories first so items in any file can reference them.
    for name, doc, _ in docs:
        for idx, raw in enumerate(doc.get("categories") or []):
            try:
                category = parse_category(raw)
                categories[category.id] = category
            except ValidationError as exc:
                errors.append(f"{name}: category #{idx + 1}: {exc}")

    for name, doc, label in docs:
        for idx, raw in enumerate(doc.get("items") or []):
            try:
                item = parse_item(raw, source=label, categories=categories)
            except (ValidationError, KeyError) as exc:
                ident = raw.get("id", f"#{idx + 1}") if isinstance(raw, dict) else f"#{idx + 1}"
                errors.append(f"{name}: item {ident}: {exc}")
                continue
            if item.id in items and label == "built-in":
                errors.append(f"{name}: duplicate built-in id '{item.id}'")
                continue
            items[item.id] = item
        for raw_id in doc.get("hide") or []:
            try:
                hidden.add(check("id", raw_id))
            except ValidationError as exc:
                errors.append(f"{name}: hide: {exc}")

    for item_id in hidden:
        items.pop(item_id, None)

    # Dangling dependencies make an item unusable; report and drop it.
    changed = True
    while changed:
        changed = False
        for item in list(items.values()):
            missing = [r for r in item.requires if r not in items]
            if missing:
                errors.append(f"{item.source}: item {item.id}: requires unknown item(s) {missing}")
                del items[item.id]
                changed = True

    for message in errors:
        log.warning("catalog: %s", message)
    return Catalog(items=items, categories=categories, errors=tuple(errors))
