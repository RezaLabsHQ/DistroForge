"""XDG Base Directory locations used by DistroForge.

Every file DistroForge reads or writes on behalf of the user lives under one of
these roots, so there is exactly one place that decides where things go.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from distroforge import __app_name__


def xdg_dir(var: str, fallback: str) -> Path:
    value = os.environ.get(var, "")
    # The spec says relative paths must be ignored.
    if value and Path(value).is_absolute():
        return Path(value)
    return Path.home() / fallback


@dataclass(frozen=True)
class AppPaths:
    config: Path
    data: Path
    state: Path
    cache: Path

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.yaml"

    @property
    def user_catalog_dir(self) -> Path:
        return self.config / "catalog.d"

    @property
    def profiles_dir(self) -> Path:
        return self.config / "profiles"

    @property
    def log_dir(self) -> Path:
        return self.state / "logs"

    def ensure(self) -> None:
        """Create the user directories with private permissions."""
        for path in (self.config, self.user_catalog_dir, self.profiles_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)


def default_paths() -> AppPaths:
    return AppPaths(
        config=xdg_dir("XDG_CONFIG_HOME", ".config") / __app_name__,
        data=xdg_dir("XDG_DATA_HOME", ".local/share") / __app_name__,
        state=xdg_dir("XDG_STATE_HOME", ".local/state") / __app_name__,
        cache=xdg_dir("XDG_CACHE_HOME", ".cache") / __app_name__,
    )
