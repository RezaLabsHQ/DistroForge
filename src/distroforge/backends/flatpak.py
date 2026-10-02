"""Flatpak — the universal fallback that works on every family."""

from __future__ import annotations

import shutil

from distroforge.backends.base import Backend
from distroforge.core.executor import Command, probe
from distroforge.engine.ops import CommandOp, Operation

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"


class FlatpakBackend(Backend):
    name = "flatpak"
    label = "Flatpak"
    id_kind = "flatpak"

    @property
    def scope_flag(self) -> str:
        return "--system" if self.options.flatpak_scope == "system" else "--user"

    @property
    def needs_root(self) -> bool:  # type: ignore[override]
        return self.options.flatpak_scope == "system"

    def ready(self) -> bool:
        return shutil.which("flatpak") is not None

    def _snapshot(self) -> frozenset[str]:
        # Lists both user and system installations.
        _, out = probe(["flatpak", "list", "--app", "--columns=application"])
        return frozenset(out.split())

    def has_flathub(self) -> bool:
        if not self.ready():
            return False
        _, out = probe(["flatpak", "remotes", self.scope_flag, "--columns=name"])
        return "flathub" in out.split()

    def add_flathub_op(self) -> Operation:
        cmd = Command(
            ("flatpak", "remote-add", self.scope_flag, "--if-not-exists", "flathub", FLATHUB_URL),
            root=self.needs_root,
        )
        return CommandOp("Add the Flathub remote", cmd)

    def install_ops(self, ids: list[str]) -> list[Operation]:
        apps = self.validate(ids)
        cmd = Command(
            ("flatpak", "install", self.scope_flag, "-y", "--noninteractive", "flathub", *apps),
            root=self.needs_root,
        )
        return [CommandOp(f"Install {', '.join(apps)} (Flathub)", cmd)]
