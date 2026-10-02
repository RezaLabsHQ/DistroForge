"""Shared fixtures: fake systems per family and fully stubbed backends.

Nothing in the unit suite touches the real package manager, sudo or network.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from distroforge.backends import Backends
from distroforge.catalog import Catalog, load_catalog
from distroforge.core.settings import Settings
from distroforge.core.system import Family, OsRelease, SystemInfo
from distroforge.engine import resolve as resolve_mod
from distroforge.engine.resolve import Environment, Resolver

OS_FOR_FAMILY = {
    Family.DEBIAN: OsRelease(id="ubuntu", id_like=("debian",), version_id="24.04", codename="noble"),
    Family.FEDORA: OsRelease(id="fedora", version_id="44"),
    Family.ARCH: OsRelease(id="arch"),
}


def make_system(family: Family, tmp_path: Path, **overrides: object) -> SystemInfo:
    base = {
        "os": OS_FOR_FAMILY.get(family, OsRelease(id="unknown")),
        "family": family,
        "arch": "x86_64",
        "username": "tester",
        "hostname": "box",
        "home": tmp_path,
    }
    base.update(overrides)
    return SystemInfo(**base)  # type: ignore[arg-type]


def stub_backends(backends: Backends, installed: Iterable[str] = (), *, ready: bool = True) -> Backends:
    """Make every backend 'ready' with a fixed installed set and no flathub probe."""
    snapshot = frozenset(installed)
    for name in ("apt", "dnf", "pacman", "aur", "flatpak"):
        backend = backends.get(name)
        backend.ready = lambda r=ready: r  # type: ignore[method-assign]
        backend._snapshot = lambda s=snapshot: s  # type: ignore[method-assign]
        backend._resolve_missing = lambda missing: set()  # type: ignore[method-assign]
    backends.flatpak.has_flathub = lambda: True  # type: ignore[method-assign]
    return backends


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return load_catalog(None)


@pytest.fixture
def make_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Environment]:
    """Factory: ``make_env(Family.FEDORA, installed={...}, applied={...})``."""

    def factory(
        family: Family = Family.FEDORA,
        *,
        installed: Iterable[str] = (),
        applied: Iterable[str] = (),
        settings: Settings | None = None,
        **system_overrides: object,
    ) -> Environment:
        system = make_system(family, tmp_path, **system_overrides)
        backends = stub_backends(Backends(system), installed)
        applied_set = set(applied)
        # Action state comes from probes of the real host; replace with a fixed set.
        monkeypatch.setattr(Resolver, "action_applied", lambda self, ref: ref.name in applied_set)
        # Binaries on the developer's machine must not leak into "is it installed?" checks.
        monkeypatch.setattr(resolve_mod.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("sh", "bash") else None)
        return Environment(system, backends, settings or Settings())

    return factory
