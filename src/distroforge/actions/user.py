"""Per-user actions: shell init snippets, git identity, Nerd Fonts, SSH keys. Never need root."""

from __future__ import annotations

import asyncio
import shutil
import tarfile
from pathlib import Path
from typing import ClassVar

from distroforge.actions.base import Action, ActionContext, Params, str_list
from distroforge.core import shellrc
from distroforge.core.executor import Command, Result, probe
from distroforge.core.net import download
from distroforge.core.validate import ValidationError, check, check_email, check_text
from distroforge.engine.ops import CommandOp, Operation, RunContext, TaskOp


def _line(value: object) -> str:
    text = check_text(value, max_len=500, field="shell line")
    return text


class ShellInit(Action):
    """Add a managed block to bash/zsh/fish startup files for shells that are installed."""

    name = "shell_init"
    title = "Configure shell startup"
    params: ClassVar = {
        "id": (True, lambda v: check("id", v)),
        "bash": (False, str_list(_line)),
        "zsh": (False, str_list(_line)),
        "fish": (False, str_list(_line)),
    }

    def parse(self, raw):  # type: ignore[no-untyped-def]
        params = super().parse(raw)
        if not any(s in params for s in shellrc.SUPPORTED_SHELLS):
            raise ValidationError("shell_init: provide lines for at least one of bash/zsh/fish")
        return params

    def _targets(self, params: Params, ctx: ActionContext) -> list[tuple[str, Path]]:
        return [
            (shell, shellrc.rc_file(shell, ctx.system.home, params["id"]))
            for shell in shellrc.SUPPORTED_SHELLS
            if shell in params and shutil.which(shell)
        ]

    def describe(self, params: Params) -> str:
        shells = "/".join(s for s in shellrc.SUPPORTED_SHELLS if s in params)
        return f"Add '{params['id']}' init to {shells} startup files"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        targets = self._targets(params, ctx)
        return bool(targets) and all(
            shellrc.file_has_block(path, params["id"], params[shell]) for shell, path in targets
        )

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        block_id = params["id"]

        async def apply(run: RunContext) -> Result:
            targets = self._targets(params, ctx)  # re-evaluated: shells may be new
            if not targets:
                return Result.skipped("None of the target shells are installed")
            changed = []
            for shell, path in targets:
                if shellrc.apply_block(path, block_id, params[shell]):
                    changed.append(str(path))
                    run.emit(f"Updated {path}")
            return Result.success("Updated " + ", ".join(changed) if changed else "Already configured")

        preview: list[str] = []
        for shell in shellrc.SUPPORTED_SHELLS:
            if shell in params:
                preview.append(
                    f"# {shellrc.rc_file(shell, ctx.system.home, block_id)} (if {shell} is installed)"
                )
                preview += [
                    "    " + line for line in shellrc.render_block(block_id, params[shell]).splitlines()
                ]
        return [TaskOp(f"Configure shell init: {block_id}", apply, preview)]


class GitIdentity(Action):
    name = "git_identity"
    title = "Configure git identity"
    params: ClassVar = {"default_branch": (False, lambda v: check("apt_token", v))}

    def _values(self, params: Params, ctx: ActionContext) -> dict[str, str]:
        values = {"init.defaultBranch": params.get("default_branch", "main")}
        if ctx.settings.git_name:
            values["user.name"] = check_text(ctx.settings.git_name, max_len=100, field="git name")
        if ctx.settings.git_email:
            values["user.email"] = check_email(ctx.settings.git_email)
        return values

    def describe(self, params: Params) -> str:
        return "Set git user.name / user.email (from Settings) and default branch"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        values = self._values(params, ctx)
        if "user.name" not in values:
            return False
        return all(
            probe(["git", "config", "--global", "--get", key])[1].strip() == value
            for key, value in values.items()
        )

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        values = self._values(params, ctx)
        ops: list[Operation] = []
        if "user.name" not in values or "user.email" not in values:

            async def missing(_: RunContext) -> Result:
                return Result.failed("Set your git name and email in Settings (key: s) first.")

            ops.append(TaskOp("Check git identity", missing, ["# requires git name/email in Settings"]))
        ops += [
            CommandOp(f"git config {key}", Command(("git", "config", "--global", key, value)))
            for key, value in values.items()
        ]
        return ops


_FONT_SUFFIXES = (".ttf", ".otf")
_FONT_URL = "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/{font}.tar.xz"


def _extract_fonts(archive: Path, dest: Path) -> int:
    """Extract only regular font files, flattened, so archive paths can't escape ``dest``."""
    count = 0
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as tar:
        for member in tar:
            name = Path(member.name).name
            if not member.isfile() or not name.lower().endswith(_FONT_SUFFIXES) or name.startswith("."):
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, open(dest / name, "wb") as out:
                shutil.copyfileobj(source, out)
            count += 1
    return count


class NerdFont(Action):
    name = "nerd_font"
    title = "Install a Nerd Font"
    params: ClassVar = {"font": (True, lambda v: check("font", v))}

    def _dir(self, params: Params, ctx: ActionContext) -> Path:
        return ctx.system.home / ".local" / "share" / "fonts" / "NerdFonts" / str(params["font"])

    def describe(self, params: Params) -> str:
        return f"Install {params['font']} Nerd Font to ~/.local/share/fonts"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        target = self._dir(params, ctx)
        return target.is_dir() and any(target.iterdir())

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        font = params["font"]
        url = _FONT_URL.format(font=font)
        target = self._dir(params, ctx)

        async def apply(run: RunContext) -> Result:
            archive = run.tempfile(f"{font}.tar.xz")
            run.emit(f"Downloading {url}")
            await asyncio.to_thread(download, url, archive, max_bytes=300 * 1024 * 1024, timeout=300)
            count = await asyncio.to_thread(_extract_fonts, archive, target)
            if count == 0:
                return Result.failed(f"No font files found in {font}.tar.xz")
            run.emit(f"Installed {count} font files to {target}")
            if shutil.which("fc-cache"):
                return await run.run(Command(("fc-cache", "-f", str(target))))
            return Result.success()

        return [
            TaskOp(
                f"Install {font} Nerd Font",
                apply,
                [f"# download {url}", f"# extract *.ttf/*.otf → {target}", "fc-cache -f"],
            )
        ]


class SshKey(Action):
    name = "ssh_key"
    title = "Generate an SSH key"
    params: ClassVar = {"comment": (False, lambda v: check_text(v, max_len=100, field="comment"))}

    def _path(self, ctx: ActionContext) -> Path:
        return ctx.system.home / ".ssh" / "id_ed25519"

    def describe(self, params: Params) -> str:
        return "Generate an Ed25519 SSH key (~/.ssh/id_ed25519) if none exists"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return self._path(ctx).exists()

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        path = self._path(ctx)
        comment = (
            params.get("comment") or ctx.settings.git_email or f"{ctx.system.username}@{ctx.system.hostname}"
        )

        async def apply(run: RunContext) -> Result:
            if path.exists():
                return Result.skipped("Key already exists")
            path.parent.mkdir(mode=0o700, exist_ok=True)
            return await run.run(
                Command(("ssh-keygen", "-q", "-t", "ed25519", "-C", comment, "-f", str(path), "-N", ""))
            )

        return [
            TaskOp(
                "Generate Ed25519 SSH key",
                apply,
                [f"ssh-keygen -t ed25519 -C {comment!r} -f {path} -N ''"],
                warning="The key has no passphrase. Add one later with: ssh-keygen -p -f ~/.ssh/id_ed25519",
            )
        ]


ACTIONS: tuple[type[Action], ...] = (ShellInit, GitIdentity, NerdFont, SshKey)
