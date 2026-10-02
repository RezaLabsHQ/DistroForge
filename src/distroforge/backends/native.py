"""Native distro package managers: apt, dnf, pacman, and AUR helpers."""

from __future__ import annotations

import shutil

from distroforge.backends.base import Backend
from distroforge.core.executor import Command, probe
from distroforge.core.system import Family
from distroforge.engine.ops import CommandOp, Operation


class AptBackend(Backend):
    name = "apt"
    label = "APT"
    family = Family.DEBIAN

    def ready(self) -> bool:
        return shutil.which("apt-get") is not None and shutil.which("dpkg-query") is not None

    def _snapshot(self) -> frozenset[str]:
        _, out = probe(["dpkg-query", "-W", "-f=${db:Status-Abbrev} ${Package}\n"])
        return frozenset(
            line.split()[1] for line in out.splitlines() if line.startswith("ii") and len(line.split()) > 1
        )

    def refresh_ops(self) -> list[Operation]:
        return [CommandOp("Refresh APT package lists", Command(("apt-get", "update"), root=True))]

    def install_ops(self, ids: list[str]) -> list[Operation]:
        pkgs = self.validate(ids)
        cmd = Command(
            ("apt-get", "install", "-y", *pkgs),
            root=True,
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        return [CommandOp(f"Install {', '.join(pkgs)}", cmd)]


class DnfBackend(Backend):
    name = "dnf"
    label = "DNF"
    family = Family.FEDORA

    def ready(self) -> bool:
        return shutil.which("dnf") is not None and shutil.which("rpm") is not None

    def _snapshot(self) -> frozenset[str]:
        _, out = probe(["rpm", "-qa", "--qf", "%{NAME}\n"])
        return frozenset(out.split())

    def _resolve_missing(self, missing: list[str]) -> set[str]:
        # Handles provides such as "npm" → nodejs-npm.
        return {name for name in missing if probe(["rpm", "-q", "--whatprovides", name])[0] == 0}

    def install_ops(self, ids: list[str]) -> list[Operation]:
        pkgs = self.validate(ids)
        return [CommandOp(f"Install {', '.join(pkgs)}", Command(("dnf", "install", "-y", *pkgs), root=True))]


class PacmanBackend(Backend):
    name = "pacman"
    label = "pacman"
    family = Family.ARCH

    def ready(self) -> bool:
        return shutil.which("pacman") is not None

    def _snapshot(self) -> frozenset[str]:
        _, out = probe(["pacman", "-Qq"])
        return frozenset(out.split())

    def _resolve_missing(self, missing: list[str]) -> set[str]:
        # `pacman -T` prints the dependencies that are NOT satisfied (handles provides).
        _, out = probe(["pacman", "-T", *missing])
        return set(missing) - set(out.split())

    def refresh_ops(self) -> list[Operation]:
        # Arch does not support partial upgrades: syncing the database without
        # upgrading (pacman -Sy) can break the system, so sync means -Syu.
        cmd = Command(("pacman", "-Syu", "--noconfirm"), root=True)
        return [CommandOp("Synchronise and upgrade (Arch requires full upgrades)", cmd)]

    def install_ops(self, ids: list[str]) -> list[Operation]:
        pkgs = self.validate(ids)
        cmd = Command(("pacman", "-S", "--needed", "--noconfirm", *pkgs), root=True)
        return [CommandOp(f"Install {', '.join(pkgs)}", cmd)]


class AurBackend(Backend):
    """AUR packages through an existing helper (paru or yay).

    The helper runs as the user (it refuses root) but invokes sudo itself to
    install the built package, so its operations still require credentials.
    """

    name = "aur"
    label = "AUR"
    family = Family.ARCH

    def supported(self) -> bool:
        return super().supported() and bool(self.system.aur_helper)

    def ready(self) -> bool:
        return bool(self.system.aur_helper) and shutil.which(self.system.aur_helper) is not None

    def _snapshot(self) -> frozenset[str]:
        _, out = probe(["pacman", "-Qq"])
        return frozenset(out.split())

    def install_ops(self, ids: list[str]) -> list[Operation]:
        pkgs = self.validate(ids)
        helper = self.system.aur_helper
        cmd = Command((helper, "-S", "--needed", "--noconfirm", *pkgs))
        return [
            CommandOp(
                f"Install {', '.join(pkgs)} from the AUR via {helper}",
                cmd,
                warning="AUR packages are user-maintained and not vetted by Arch.",
                needs_root=True,
            )
        ]
