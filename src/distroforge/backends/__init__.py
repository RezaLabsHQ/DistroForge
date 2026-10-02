"""Backend registry — the single place that knows which package managers exist."""

from __future__ import annotations

from distroforge.backends.base import Backend, BackendOptions
from distroforge.backends.flatpak import FlatpakBackend
from distroforge.backends.native import AptBackend, AurBackend, DnfBackend, PacmanBackend
from distroforge.core.system import SystemInfo

BACKEND_TYPES: tuple[type[Backend], ...] = (
    AptBackend,
    DnfBackend,
    PacmanBackend,
    AurBackend,
    FlatpakBackend,
)
BACKEND_NAMES = frozenset(cls.name for cls in BACKEND_TYPES)
NATIVE_NAMES = frozenset({"apt", "dnf", "pacman"})


class Backends:
    def __init__(self, system: SystemInfo, options: BackendOptions | None = None) -> None:
        self.system = system
        self.options = options or BackendOptions()
        self._by_name: dict[str, Backend] = {cls.name: cls(system, self.options) for cls in BACKEND_TYPES}

    def get(self, name: str) -> Backend:
        return self._by_name[name]

    def supported(self, name: str) -> bool:
        backend = self._by_name.get(name)
        return backend is not None and backend.supported()

    @property
    def flatpak(self) -> FlatpakBackend:
        backend = self._by_name["flatpak"]
        assert isinstance(backend, FlatpakBackend)
        return backend

    def invalidate(self) -> None:
        for backend in self._by_name.values():
            backend.invalidate()


__all__ = ["BACKEND_NAMES", "NATIVE_NAMES", "Backend", "BackendOptions", "Backends"]
