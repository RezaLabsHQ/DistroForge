"""System-level actions: services, groups, sysctl, kernel modules, firewall, upgrades, login shell."""

from __future__ import annotations

import asyncio
import pwd
import shutil
from pathlib import Path
from typing import ClassVar

from distroforge.actions.base import Action, ActionContext, Params, boolean
from distroforge.core.executor import Command, Result, probe
from distroforge.core.system import Family, SystemInfo
from distroforge.core.validate import check
from distroforge.engine.ops import CommandOp, Operation, RunContext, TaskOp, install_root_file


class Service(Action):
    name = "service"
    title = "Enable a systemd unit"
    params: ClassVar = {
        "unit": (True, lambda v: check("unit", v)),
        "user": (False, boolean),
        "now": (False, boolean),
    }

    def _base(self, params: Params) -> tuple[str, ...]:
        return ("systemctl", "--user") if params.get("user") else ("systemctl",)

    def describe(self, params: Params) -> str:
        return f"Enable {params['unit']}"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        _, out = probe([*self._base(params), "is-enabled", params["unit"]])
        return out.strip() in ("enabled", "static", "alias")

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        argv = [*self._base(params), "enable"]
        if params.get("now", True):
            argv.append("--now")
        argv.append(params["unit"])
        cmd = Command(tuple(argv), root=not params.get("user"))
        return [CommandOp(f"Enable {params['unit']}", cmd)]


class UserGroup(Action):
    name = "user_group"
    title = "Add your user to a group"
    params: ClassVar = {
        "group": (True, lambda v: check("group", v)),
        "create": (False, boolean),
    }

    def describe(self, params: Params) -> str:
        return f"Add {params['group']} group membership (takes effect after re-login)"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        _, out = probe(["id", "-nG", ctx.system.username])
        return params["group"] in out.split()

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        user = check("group", ctx.system.username)  # same rules as POSIX user names
        ops: list[Operation] = []
        if params.get("create"):
            ops.append(
                CommandOp(
                    f"Create group {params['group']}", Command(("groupadd", "-f", params["group"]), root=True)
                )
            )
        ops.append(
            CommandOp(
                f"Add {user} to {params['group']}",
                Command(("usermod", "-aG", params["group"], user), root=True),
            )
        )
        return ops


class Sysctl(Action):
    name = "sysctl"
    title = "Set a kernel parameter"
    params: ClassVar = {
        "key": (True, lambda v: check("sysctl_key", v)),
        "value": (True, lambda v: check("sysctl_value", str(v))),
    }

    def _file(self, params: Params) -> str:
        return f"/etc/sysctl.d/99-distroforge-{params['key'].replace('.', '-').replace('_', '-')}.conf"

    def _content(self, params: Params) -> str:
        return f"{params['key']} = {params['value']}\n"

    def describe(self, params: Params) -> str:
        return f"Set {params['key']} = {params['value']} (persistent)"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        path = Path(self._file(params))
        return path.exists() and path.read_text(encoding="utf-8") == self._content(params)

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        path = self._file(params)
        return [
            install_root_file(f"Persist {params['key']}", path, content=self._content(params)),
            CommandOp(f"Apply {params['key']}", Command(("sysctl", "-p", path), root=True)),
        ]


class KernelModule(Action):
    name = "kernel_module"
    title = "Load a kernel module at boot"
    params: ClassVar = {"module": (True, lambda v: check("module", v))}

    def _file(self, params: Params) -> str:
        return f"/etc/modules-load.d/distroforge-{params['module']}.conf"

    def describe(self, params: Params) -> str:
        return f"Load kernel module {params['module']} now and at boot"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return Path(self._file(params)).exists()

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        return [
            install_root_file(
                f"Persist {params['module']}", self._file(params), content=params["module"] + "\n"
            ),
            CommandOp(f"Load {params['module']}", Command(("modprobe", params["module"]), root=True)),
        ]


class Firewall(Action):
    """firewalld on Fedora, ufw elsewhere: deny incoming, allow outgoing."""

    name = "firewall"
    title = "Enable the firewall"

    def describe(self, params: Params) -> str:
        return "Enable firewall (deny incoming, allow outgoing)"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        if ctx.system.family is Family.FEDORA:
            return probe(["systemctl", "is-active", "firewalld"])[1].strip() == "active"
        conf = Path("/etc/ufw/ufw.conf")
        return conf.exists() and "ENABLED=yes" in conf.read_text(encoding="utf-8", errors="replace")

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        if ctx.system.family is Family.FEDORA:
            return [
                CommandOp(
                    "Enable firewalld", Command(("systemctl", "enable", "--now", "firewalld"), root=True)
                )
            ]
        ops: list[Operation] = [
            CommandOp("Deny incoming by default", Command(("ufw", "default", "deny", "incoming"), root=True)),
            CommandOp(
                "Allow outgoing by default", Command(("ufw", "default", "allow", "outgoing"), root=True)
            ),
            CommandOp("Enable ufw", Command(("ufw", "--force", "enable"), root=True)),
        ]
        if ctx.system.family is Family.ARCH:
            ops.append(
                CommandOp("Start ufw at boot", Command(("systemctl", "enable", "--now", "ufw"), root=True))
            )
        return ops


class SystemUpgrade(Action):
    name = "system_upgrade"
    title = "Upgrade all packages"
    early = True

    def supported(self, system: SystemInfo, params: Params) -> bool:
        return system.family is not Family.UNKNOWN

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return False  # always worth running when selected

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        family = ctx.system.family
        if family is Family.DEBIAN:
            env = {"DEBIAN_FRONTEND": "noninteractive"}
            return [
                CommandOp("Refresh APT package lists", Command(("apt-get", "update"), root=True)),
                CommandOp(
                    "Upgrade all packages", Command(("apt-get", "dist-upgrade", "-y"), root=True, env=env)
                ),
            ]
        if family is Family.FEDORA:
            return [
                CommandOp("Upgrade all packages", Command(("dnf", "upgrade", "-y", "--refresh"), root=True))
            ]
        return [CommandOp("Upgrade all packages", Command(("pacman", "-Syu", "--noconfirm"), root=True))]


class DefaultShell(Action):
    name = "default_shell"
    title = "Change your login shell"
    params: ClassVar = {"shell": (True, lambda v: check("shell", v))}

    def describe(self, params: Params) -> str:
        return f"Make {params['shell']} your login shell"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        try:
            current = pwd.getpwnam(ctx.system.username).pw_shell
        except KeyError:
            return False
        return Path(current).name == str(params["shell"])

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        shell = params["shell"]
        user = check("group", ctx.system.username)

        async def apply(run: RunContext) -> Result:
            # Resolved at run time: the shell may be installed earlier in the same plan.
            path = shutil.which(shell)
            if not path:
                return Result.failed(f"{shell} is not installed")
            etc_shells = await asyncio.to_thread(Path("/etc/shells").read_text, encoding="utf-8")
            shells = etc_shells.split()
            if path not in shells:
                return Result.failed(f"{path} is not listed in /etc/shells")
            return await run.run(Command(("usermod", "--shell", path, user), root=True))

        return [
            TaskOp(
                f"Set login shell to {shell}",
                apply,
                [f"sudo usermod --shell $(command -v {shell}) {user}"],
                needs_root=True,
            )
        ]


ACTIONS: tuple[type[Action], ...] = (
    Service,
    UserGroup,
    Sysctl,
    KernelModule,
    Firewall,
    SystemUpgrade,
    DefaultShell,
)
