"""Catalog data model and strict parsing.

A catalog item describes *what* to install and every *way* to install it; the
planner picks the way that fits the current system and the user's preference.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from distroforge.actions import get_action
from distroforge.backends import BACKEND_NAMES, NATIVE_NAMES
from distroforge.core.system import Family, OsRelease, SystemInfo
from distroforge.core.validate import (
    ValidationError,
    check,
    check_https_url,
    check_text,
)

ITEM_KINDS = ("app", "tweak")
SCRIPT_SHELLS = ("sh", "bash")

# Values used to validate placeholder-bearing params when the catalog loads.
_SAMPLE_SYSTEM = SystemInfo(
    os=OsRelease(id="ubuntu", codename="noble", version_id="24.04"),
    family=Family.DEBIAN,
    arch="x86_64",
    username="user",
)


PLACEHOLDER_NAMES = frozenset({"home", "user", "arch", "codename", "apt_os", "version_id"})
_PLACEHOLDER = re.compile(r"\{(" + "|".join(sorted(PLACEHOLDER_NAMES)) + r")\}")


def substitute(value: Any, placeholders: Mapping[str, str]) -> Any:
    """Recursively replace the known ``{name}`` placeholders in strings.

    Only names in :data:`PLACEHOLDER_NAMES` are touched, so shell syntax such as
    ``${VAR}`` or ``{ cmd; }`` in shell-init lines passes through unchanged.
    """
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda m: placeholders[m.group(1)], value)
    if isinstance(value, list):
        return [substitute(v, placeholders) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, placeholders) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class ActionRef:
    name: str
    raw: Mapping[str, Any]

    def resolve(self, system: SystemInfo) -> dict[str, Any]:
        return get_action(self.name).parse(substitute(dict(self.raw), system.placeholders()))

    def supported(self, system: SystemInfo) -> bool:
        try:
            params = self.resolve(system)
        except ValidationError:
            return False
        return get_action(self.name).supported(system, params)

    def describe(self, system: SystemInfo) -> str:
        action = get_action(self.name)
        try:
            return action.describe(self.resolve(system))
        except ValidationError:
            return action.title


@dataclass(frozen=True)
class ScriptSpec:
    url: str
    shell: str = "sh"
    sha256: str = ""
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)

    @property
    def host(self) -> str:
        return self.url.split("/")[2]


@dataclass(frozen=True)
class Method:
    backend: str  # apt | dnf | pacman | aur | flatpak | script
    packages: tuple[str, ...] = ()
    script: ScriptSpec | None = None
    pre: tuple[ActionRef, ...] = ()
    post: tuple[ActionRef, ...] = ()
    distros: tuple[str, ...] = ()  # optional os-release ID / ID_LIKE filter

    @property
    def native(self) -> bool:
        return self.backend in NATIVE_NAMES

    @property
    def label(self) -> str:
        return {"script": "upstream script", "aur": "AUR"}.get(self.backend, self.backend)

    def matches_distro(self, system: SystemInfo) -> bool:
        return not self.distros or bool(set(self.distros) & system.os.tokens)


@dataclass(frozen=True)
class Check:
    bins: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    flatpaks: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.bins or self.paths or self.flatpaks)


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    category: str
    description: str = ""
    kind: str = "app"
    homepage: str = ""
    methods: tuple[Method, ...] = ()
    post: tuple[ActionRef, ...] = ()
    requires: tuple[str, ...] = ()
    check: Check = field(default_factory=Check)
    notes: str = ""
    source: str = "built-in"

    def search_text(self) -> str:
        return f"{self.id} {self.name} {self.description} {self.category}".lower()


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    icon: str = "•"
    order: int = 100


@dataclass(frozen=True)
class Catalog:
    items: Mapping[str, Item]
    categories: Mapping[str, Category]
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", MappingProxyType(dict(self.items)))
        object.__setattr__(self, "categories", MappingProxyType(dict(self.categories)))

    def by_category(self) -> dict[str, list[Item]]:
        grouped: dict[str, list[Item]] = {cid: [] for cid in self.sorted_category_ids()}
        for item in sorted(self.items.values(), key=lambda i: i.name.lower()):
            grouped.setdefault(item.category, []).append(item)
        return {k: v for k, v in grouped.items() if v}

    def sorted_category_ids(self) -> list[str]:
        return [c.id for c in sorted(self.categories.values(), key=lambda c: (c.order, c.name))]


# ── Parsing ─────────────────────────────────────────


def _as_list(value: Any, what: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        return [value]
    if isinstance(value, list):
        return value
    raise ValidationError(f"{what} must be a list")


def _mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{what} must be a mapping, got {type(value).__name__}")
    return value


def parse_action_ref(raw: Any) -> ActionRef:
    data = dict(_mapping(raw, "action"))
    name = data.pop("action", None)
    if not isinstance(name, str):
        raise ValidationError(f"Action entries need an 'action' key: {raw!r}")
    action = get_action(name)
    # Validate now (with sample placeholder values) so errors surface at load time.
    action.parse(substitute(data, _SAMPLE_SYSTEM.placeholders()))
    return ActionRef(name, MappingProxyType(data))


def parse_script(raw: Any) -> ScriptSpec:
    data = _mapping(raw, "script")
    unknown = set(data) - {"url", "shell", "sha256", "args", "env"}
    if unknown:
        raise ValidationError(f"script: unknown key(s) {sorted(unknown)}")
    shell = data.get("shell", "sh")
    if shell not in SCRIPT_SHELLS:
        raise ValidationError(f"script.shell must be one of {SCRIPT_SHELLS}")
    sha = data.get("sha256", "")
    if sha and (
        not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdefABCDEF" for c in sha)
    ):
        raise ValidationError("script.sha256 must be a 64-character hex digest")
    args = tuple(
        check_text(a, max_len=200, field="script argument") for a in _as_list(data.get("args"), "args")
    )
    env = {
        check("env_key", k): check_text(v, max_len=200, field="script env value")
        for k, v in _mapping(data.get("env", {}), "script.env").items()
    }
    return ScriptSpec(
        url=check_https_url(data.get("url")), shell=shell, sha256=sha, args=args, env=MappingProxyType(env)
    )


def parse_method(raw: Any) -> Method:
    data = dict(_mapping(raw, "install method"))
    pre = tuple(parse_action_ref(a) for a in _as_list(data.pop("pre", None), "pre"))
    post = tuple(parse_action_ref(a) for a in _as_list(data.pop("post", None), "post"))
    distros = tuple(check("id", d) for d in _as_list(data.pop("distros", None), "distros"))
    backends = [k for k in data if k in BACKEND_NAMES or k == "script"]
    if len(backends) != 1 or len(data) != 1:
        raise ValidationError(
            f"Each install method needs exactly one of {sorted(BACKEND_NAMES | {'script'})}: {raw!r}"
        )
    backend = backends[0]
    if backend == "script":
        return Method("script", script=parse_script(data["script"]), pre=pre, post=post, distros=distros)
    kind = "flatpak" if backend == "flatpak" else "package"
    packages = tuple(check(kind, p) for p in _as_list(data[backend], backend))
    if not packages:
        raise ValidationError(f"{backend}: no packages listed")
    return Method(backend, packages=packages, pre=pre, post=post, distros=distros)


def parse_check(raw: Any) -> Check:
    if raw is None:
        return Check()
    data = _mapping(raw, "check")
    unknown = set(data) - {"bin", "path", "flatpak"}
    if unknown:
        raise ValidationError(f"check: unknown key(s) {sorted(unknown)}")
    paths = []
    for p in _as_list(data.get("path"), "check.path"):
        path = check_text(p, max_len=200, field="check path")
        if not path.startswith(("/", "{home}/")):
            raise ValidationError(f"check.path must be absolute or start with {{home}}/: {p!r}")
        paths.append(path)
    return Check(
        bins=tuple(check("binary", b) for b in _as_list(data.get("bin"), "check.bin")),
        paths=tuple(paths),
        flatpaks=tuple(check("flatpak", f) for f in _as_list(data.get("flatpak"), "check.flatpak")),
    )


_ITEM_KEYS = {
    "id",
    "name",
    "category",
    "description",
    "kind",
    "homepage",
    "install",
    "post",
    "requires",
    "check",
    "notes",
}


def parse_item(raw: Any, *, source: str, categories: Mapping[str, Category]) -> Item:
    data = _mapping(raw, "item")
    unknown = set(data) - _ITEM_KEYS
    if unknown:
        raise ValidationError(f"unknown key(s) {sorted(unknown)}")
    item_id = check("id", data.get("id"))
    category = check("id", data.get("category"))
    if category not in categories:
        raise ValidationError(f"{item_id}: unknown category '{category}'")
    kind = data.get("kind", "app")
    if kind not in ITEM_KINDS:
        raise ValidationError(f"{item_id}: kind must be one of {ITEM_KINDS}")
    homepage = data.get("homepage", "")
    if homepage:
        check_https_url(homepage)

    methods = tuple(parse_method(m) for m in _as_list(data.get("install"), "install"))
    post = tuple(parse_action_ref(a) for a in _as_list(data.get("post"), "post"))
    item_check = parse_check(data.get("check"))
    if not methods and not post:
        raise ValidationError(f"{item_id}: needs at least one install method or post action")
    if any(m.backend == "script" for m in methods) and not item_check:
        raise ValidationError(f"{item_id}: items installed by script need a 'check' (bin/path)")

    return Item(
        id=item_id,
        name=check_text(data.get("name"), max_len=60, field="name"),
        category=category,
        description=check_text(data.get("description", ""), max_len=200, field="description"),
        kind=kind,
        homepage=homepage,
        methods=methods,
        post=post,
        requires=tuple(check("id", r) for r in _as_list(data.get("requires"), "requires")),
        check=item_check,
        notes=check_text(data.get("notes", ""), max_len=400, field="notes"),
        source=source,
    )


def parse_category(raw: Any) -> Category:
    data = _mapping(raw, "category")
    order = data.get("order", 100)
    if not isinstance(order, int):
        raise ValidationError("category.order must be an integer")
    return Category(
        id=check("id", data.get("id")),
        name=check_text(data.get("name"), max_len=40, field="category name"),
        icon=check_text(data.get("icon", "•"), max_len=4, field="icon"),
        order=order,
    )
