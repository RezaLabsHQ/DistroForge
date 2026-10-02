"""Regenerate the README screenshots from a deterministic demo system.

    python scripts/screenshots.py

Nothing is installed or probed on the host: backends and action state are stubbed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from distroforge.backends import Backends
from distroforge.catalog import load_catalog
from distroforge.core.paths import AppPaths
from distroforge.core.settings import Settings
from distroforge.core.system import Family, GpuVendor, OsRelease, SystemInfo
from distroforge.engine.resolve import Resolver
from distroforge.services import Services
from distroforge.tui.app import DistroForgeApp

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
SIZE = (150, 42)
INSTALLED = {
    "git",
    "curl",
    "wget",
    "htop",
    "flatpak",
    "firefox",
    "rsync",
    "tree",
    "openssh-clients",
    "gnupg2",
}


def demo_services(theme: str) -> Services:
    system = SystemInfo(
        os=OsRelease(id="fedora", version_id="44", pretty_name="Fedora Linux 44 (Workstation Edition)"),
        family=Family.FEDORA,
        arch="x86_64",
        kernel="7.2.8-200.fc44.x86_64",
        cpu="AMD Ryzen 7 7800X3D 8-Core Processor",
        ram_gb=32,
        gpu_vendor=GpuVendor.AMD,
        gpu_name="AMD Radeon RX 7800 XT",
        hostname="forge",
        username="you",
        home=Path("/home/you"),  # display only: screenshots are dry runs
        desktop="GNOME",
        session_type="wayland",
        has_flatpak=True,
    )
    backends = Backends(system)
    for name in ("dnf", "flatpak"):
        backend = backends.get(name)
        backend.ready = lambda: True  # type: ignore[method-assign]
        backend._snapshot = lambda: frozenset(INSTALLED)  # type: ignore[method-assign]
        backend._resolve_missing = lambda missing: set()  # type: ignore[method-assign]
    backends.flatpak.has_flathub = lambda: True  # type: ignore[method-assign]
    Resolver.action_applied = lambda self, ref: ref.name == "flathub"  # type: ignore[method-assign]
    # Display-only paths; screenshots never save settings or profiles.
    paths = AppPaths(
        *(
            Path("/home/you") / p / "distroforge"
            for p in (".config", ".local/share", ".local/state", ".cache")
        )
    )
    log = Path("/home/you/.local/state/distroforge/logs/distroforge-20261002-120000.log")
    return Services(paths, Settings(theme=theme), system, load_catalog(), backends, log)


async def shoot(name: str, theme: str, keys: list[str], *, wait: float = 0.8) -> None:
    app = DistroForgeApp(demo_services(theme), dry_run=True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.8)
        for key in keys:
            if key.startswith("@"):
                await pilot.pause(float(key[1:]))
            else:
                await pilot.press(key)
        await pilot.pause(wait)
        app.save_screenshot(str(OUT / f"{name}.svg"))
        print("wrote", OUT / f"{name}.svg")


SELECT_DEV = [
    key
    for name in ("docker", "starship", "vscode", "obsidian")
    for key in ("slash", *name, "enter", "space", "escape")
]


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    await shoot("main", "catppuccin-mocha", [*SELECT_DEV, "down", "down"])
    await shoot("review", "catppuccin-mocha", [*SELECT_DEV, "r", "@1.5"])
    await shoot("run", "catppuccin-mocha", [*SELECT_DEV, "r", "@1.5", "enter", "@1.5"])
    await shoot("latte", "catppuccin-latte", ["down", "down", "down", "space", "down", "space"])
    await shoot("profiles", "forge", ["p", "@0.5"])
    await shoot("help", "catppuccin-macchiato", ["question_mark", "@0.5"])


if __name__ == "__main__":
    asyncio.run(main())
