"""Package backend interface.

A backend turns a list of package identifiers into operations, and answers
"is this installed?" from one cached snapshot of the package database.
Adding a new package manager means adding one subclass and registering it.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from distroforge.core.system import Family, SystemInfo
from distroforge.core.validate import check
from distroforge.engine.ops import Operation


@dataclass(frozen=True)
class BackendOptions:
    flatpak_scope: str = "user"  # "user" (no root needed) or "system"


class Backend(ABC):
    #: Key used in catalog files (``apt:``, ``dnf:`` …).
    name: str
    label: str
    #: Validation pattern for identifiers (see :mod:`distroforge.core.validate`).
    id_kind: str = "package"
    #: Native backends belong to one family; universal ones work everywhere.
    family: Family | None = None
    #: Whether install operations need root.
    needs_root: bool = True

    def __init__(self, system: SystemInfo, options: BackendOptions) -> None:
        self.system = system
        self.options = options
        self._lock = threading.Lock()
        self._installed: frozenset[str] | None = None

    # ── availability ──
    def supported(self) -> bool:
        """Can this backend be used on this system (possibly after bootstrapping)?"""
        return self.family is None or self.family is self.system.family

    @abstractmethod
    def ready(self) -> bool:
        """Is the tool present right now?"""

    # ── state ──
    @abstractmethod
    def _snapshot(self) -> frozenset[str]:
        """Return all installed identifiers."""

    def _resolve_missing(self, missing: list[str]) -> set[str]:
        """Second-chance check for names that are virtual/provided. Returns found names."""
        return set()

    def installed_set(self) -> frozenset[str]:
        with self._lock:
            if self._installed is None:
                self._installed = self._snapshot() if self.ready() else frozenset()
            return self._installed

    def invalidate(self) -> None:
        with self._lock:
            self._installed = None

    def is_installed(self, ids: Iterable[str]) -> bool:
        wanted = list(ids)
        if not wanted or not self.ready():
            return False
        installed = self.installed_set()
        missing = [p for p in wanted if p not in installed]
        if not missing:
            return True
        return set(missing) <= self._resolve_missing(missing)

    # ── operations ──
    def validate(self, ids: Iterable[str]) -> list[str]:
        return [check(self.id_kind, i) for i in ids]

    def refresh_ops(self) -> list[Operation]:
        """Operations to run once before installing (metadata refresh)."""
        return []

    @abstractmethod
    def install_ops(self, ids: list[str]) -> list[Operation]: ...
