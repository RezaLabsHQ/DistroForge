"""Method selection and installed-state inspection for catalog items."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from distroforge.actions import ActionContext, get_action
from distroforge.backends import Backends
from distroforge.catalog.models import ActionRef, Item, Method, substitute
from distroforge.core.executor import Command, Result
from distroforge.core.net import download
from distroforge.core.settings import Settings
from distroforge.core.system import Family, SystemInfo
from distroforge.core.validate import ValidationError
from distroforge.engine.ops import Operation, RunContext, TaskOp

# Lower rank wins. Scripts are always the last resort.
_RANK = {
    "native": {"native": 0, "aur": 1, "flatpak": 2, "script": 3},
    "flatpak": {"flatpak": 0, "native": 1, "aur": 2, "script": 3},
}

_USER_BIN_DIRS = (".local/bin", ".cargo/bin")


@dataclass(frozen=True)
class Environment:
    system: SystemInfo
    backends: Backends
    settings: Settings

    @property
    def action_context(self) -> ActionContext:
        return ActionContext(self.system, self.backends, self.settings)


class Resolver:
    """Answers: how can this item be installed here, and is it already done?"""

    def __init__(self, env: Environment) -> None:
        self.env = env

    # ── method selection ──

    def _method_usable(self, method: Method) -> bool:
        if not method.matches_distro(self.env.system):
            return False
        if method.backend == "script":
            ok = shutil.which(method.script.shell if method.script else "sh") is not None
        elif method.backend == "flatpak":
            # Usable if present, or if we can install it with a known package manager.
            ok = self.env.backends.flatpak.ready() or self.env.system.family is not Family.UNKNOWN
        else:
            ok = self.env.backends.supported(method.backend)
        return ok and all(ref.supported(self.env.system) for ref in (*method.pre, *method.post))

    def candidates(self, item: Item) -> list[Method]:
        rank = _RANK[self.env.settings.prefer]
        usable = [m for m in item.methods if self._method_usable(m)]
        return sorted(usable, key=lambda m: rank["native" if m.native else m.backend])

    def supported(self, item: Item) -> bool:
        if item.methods and not self.candidates(item):
            return False
        return all(ref.supported(self.env.system) for ref in item.post)

    def choose(self, item: Item, override: str | None = None) -> Method | None:
        """Pick the method for ``item``; ``override`` is a backend name the user chose."""
        candidates = self.candidates(item)
        if override:
            for method in candidates:
                if method.backend == override:
                    return method
        return candidates[0] if candidates else None

    def unsupported_reason(self, item: Item) -> str:
        if item.methods and not self.candidates(item):
            available = ", ".join(sorted({m.label for m in item.methods}))
            return f"No install method for {self.env.system.family.label} (available: {available})"
        return "Not applicable to this system"

    # ── state ──

    def action_applied(self, ref: ActionRef) -> bool:
        try:
            params = ref.resolve(self.env.system)
            return get_action(ref.name).is_applied(params, self.env.action_context) is True
        except (ValidationError, OSError):
            return False

    def check_hit(self, item: Item) -> bool:
        home = self.env.system.home
        for binary in item.check.bins:
            if shutil.which(binary):
                return True
            for rel in _USER_BIN_DIRS:
                candidate = home / rel / binary
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return True
        for raw in item.check.paths:
            if Path(substitute(raw, self.env.system.placeholders())).exists():
                return True
        flatpaks = self.env.backends.flatpak
        return any(f in flatpaks.installed_set() for f in item.check.flatpaks)

    def packages_installed(self, method: Method) -> bool:
        if method.backend == "script" or not method.packages:
            return False
        return self.env.backends.get(method.backend).is_installed(method.packages)

    def is_installed(self, item: Item, method: Method | None = None) -> bool:
        """True when every part of the item (packages and actions) is in place."""
        method = method or self.choose(item)
        if item.check:
            core = self.check_hit(item)
        elif method is not None:
            # Any installed method counts (e.g. Firefox from Flathub *or* dnf).
            core = any(self.packages_installed(m) for m in self.candidates(item))
        else:
            core = True
        if not core:
            return False
        refs = [*item.post, *(method.post if method else ())]
        return all(self.action_applied(ref) for ref in refs)

    def action_ops(self, ref: ActionRef) -> list[Operation]:
        params = ref.resolve(self.env.system)
        return get_action(ref.name).ops(params, self.env.action_context)


def script_op(item: Item, method: Method, system: SystemInfo) -> TaskOp:
    """Download an upstream installer to a private dir and run it as the user."""
    spec = method.script
    assert spec is not None
    placeholders = system.placeholders()
    args = [substitute(a, placeholders) for a in spec.args]
    env = dict(spec.env)
    checksum = f"sha256 {spec.sha256}" if spec.sha256 else "no pinned checksum"

    async def apply(ctx: RunContext) -> Result:
        script = ctx.tempfile(f"{item.id}-install.sh")
        ctx.emit(f"Downloading {spec.url}")
        digest = await asyncio.to_thread(
            download, spec.url, script, max_bytes=5 * 1024 * 1024, sha256=spec.sha256 or None
        )
        ctx.emit(f"Downloaded installer, sha256 {digest}")
        (system.home / ".local" / "bin").mkdir(parents=True, exist_ok=True)
        return await ctx.run(Command((spec.shell, str(script), *args), env=env, timeout=1800))

    preview = [
        f"# download {spec.url} ({checksum}) into a private temp dir, then run as {system.username}:",
        Command((spec.shell, "<installer>", *args), env=env).display(),
    ]
    return TaskOp(
        f"Install {item.name} with the upstream installer",
        apply,
        preview,
        warning=f"Runs a remote script from {spec.host} ({checksum}).",
    )
