"""Desktop integration: app-menu entry, icon and shell completions (per user).

The menu entry uses ``Terminal=true``, so launching DistroForge from the app
menu opens it full-screen in the user's terminal — exactly like btop.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from distroforge import __version__
from distroforge.core.paths import xdg_dir
from distroforge.core.shellrc import atomic_write

APP_ID = "distroforge"


@dataclass(frozen=True)
class Targets:
    desktop: Path
    icon: Path
    bash: Path
    zsh: Path
    fish: Path

    def all(self) -> tuple[Path, ...]:
        return (self.desktop, self.icon, self.bash, self.zsh, self.fish)


def targets() -> Targets:
    data = xdg_dir("XDG_DATA_HOME", ".local/share")
    config = xdg_dir("XDG_CONFIG_HOME", ".config")
    return Targets(
        desktop=data / "applications" / f"{APP_ID}.desktop",
        icon=data / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
        bash=data / "bash-completion" / "completions" / APP_ID,
        zsh=data / "zsh" / "site-functions" / f"_{APP_ID}",
        fish=config / "fish" / "completions" / f"{APP_ID}.fish",
    )


def _desktop_quote(arg: str) -> str:
    """Quote an Exec argument per the Desktop Entry spec."""
    if not any(ch in arg for ch in " \t\n\"'\\><~|&;$*?#()`"):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def desktop_entry(executable: str) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.5",
            "Name=DistroForge",
            "GenericName=Linux Setup Toolbox",
            "Comment=Pick apps and tweaks, then install them on any Linux distro",
            f"Exec={_desktop_quote(executable)} tui",
            f"TryExec={_desktop_quote(executable)}",
            f"Icon={APP_ID}",
            "Terminal=true",
            "Categories=System;PackageManager;",
            "Keywords=setup;install;packages;apps;flatpak;apt;dnf;pacman;tweaks;",
            "StartupNotify=false",
            f"X-DistroForge-Version={__version__}",
            "",
        ]
    )


def _asset(*parts: str) -> str:
    return (resources.files("distroforge") / "assets").joinpath(*parts).read_text(encoding="utf-8")


def _refresh_caches(data_home: Path) -> None:
    """Best effort: menus pick the entry up immediately instead of after re-login."""
    for argv in (
        ["update-desktop-database", "-q", str(data_home / "applications")],
        ["gtk-update-icon-cache", "-q", "-t", "-f", str(data_home / "icons" / "hicolor")],
        ["kbuildsycoca6", "--noincremental"],
        ["kbuildsycoca5", "--noincremental"],
    ):
        if shutil.which(argv[0]):
            subprocess.run(argv, check=False, capture_output=True, timeout=60)


def resolve_executable() -> str:
    """Absolute path of the installed ``distroforge`` launcher."""
    # Keep the launcher path itself (e.g. ~/.local/bin/distroforge) so upgrades stay valid.
    found = shutil.which(APP_ID)
    if found:
        return str(Path(found).absolute())
    argv0 = Path(sys.argv[0])
    if argv0.name == APP_ID and argv0.exists():
        return str(argv0.resolve())
    raise FileNotFoundError("Could not find the 'distroforge' executable on PATH")


def install(executable: str | None = None) -> list[Path]:
    exe = executable or resolve_executable()
    t = targets()
    files = {
        t.desktop: desktop_entry(exe),
        t.icon: _asset("distroforge.svg"),
        t.bash: _asset("completions", "distroforge.bash"),
        t.zsh: _asset("completions", "_distroforge"),
        t.fish: _asset("completions", "distroforge.fish"),
    }
    for path, content in files.items():
        atomic_write(path, content)
    _refresh_caches(t.desktop.parents[1])
    return list(files)


def remove() -> list[Path]:
    removed = []
    for path in targets().all():
        if path.exists():
            path.unlink()
            removed.append(path)
    _refresh_caches(targets().desktop.parents[1])
    return removed
