"""Application bootstrap shared by the TUI and the headless CLI.

Everything a front-end needs — paths, settings, detected system, catalog,
backends — is assembled here once, so both front-ends behave identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from distroforge.backends import BackendOptions, Backends
from distroforge.catalog import Catalog, load_catalog
from distroforge.core.logging import get_logger, setup_logging
from distroforge.core.paths import AppPaths, default_paths
from distroforge.core.settings import Settings, load_settings, save_settings
from distroforge.core.system import Family, SystemInfo, detect_system
from distroforge.engine.planner import Planner
from distroforge.engine.resolve import Environment, Resolver

log = get_logger()


@dataclass
class Services:
    paths: AppPaths
    settings: Settings
    system: SystemInfo
    catalog: Catalog
    backends: Backends
    log_file: Path

    @property
    def env(self) -> Environment:
        return Environment(self.system, self.backends, self.settings)

    def resolver(self) -> Resolver:
        return Resolver(self.env)

    def planner(self) -> Planner:
        return Planner(self.catalog, self.env)

    def update_settings(self, settings: Settings) -> None:
        settings = settings.validated()
        if settings.flatpak_scope != self.settings.flatpak_scope:
            self.backends = Backends(self.system, BackendOptions(flatpak_scope=settings.flatpak_scope))
        self.settings = settings
        save_settings(self.paths.settings_file, settings)

    def reload_catalog(self) -> None:
        self.catalog = load_catalog(self.paths.user_catalog_dir)

    def refresh_state(self) -> None:
        """Forget cached package snapshots (call after a run)."""
        self.backends.invalidate()


def bootstrap(*, family: Family | None = None, paths: AppPaths | None = None) -> Services:
    paths = paths or default_paths()
    paths.ensure()
    log_file = setup_logging(paths.log_dir)
    settings = load_settings(paths.settings_file)
    system = detect_system()
    if family is not None:
        system = system.with_family(family)
    log.info(
        "DistroForge starting: %s (%s family), arch=%s, user=%s",
        system.distro_name,
        system.family.value,
        system.arch,
        system.username,
    )
    catalog = load_catalog(paths.user_catalog_dir)
    backends = Backends(system, BackendOptions(flatpak_scope=settings.flatpak_scope))
    return Services(paths, settings, system, catalog, backends, log_file)


__all__ = ["Services", "bootstrap"]
