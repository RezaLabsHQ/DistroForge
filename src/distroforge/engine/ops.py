"""Operations: the smallest unit of work in a plan.

An operation is either a :class:`CommandOp` (one argv) or a :class:`TaskOp`
(Python logic such as downloading a key and installing it with ``sudo install``).
Both expose ``preview()`` so the Review screen shows *exactly* what will happen
before anything runs, and both run through :class:`RunContext`.
"""

from __future__ import annotations

import asyncio
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from distroforge.core.executor import Command, Executor, OutputCallback, Result, Status
from distroforge.core.net import DownloadError, download
from distroforge.core.system import SystemInfo
from distroforge.core.validate import check_path_within

# The only locations DistroForge will ever write as root.
ROOT_WRITE_ROOTS = (
    "/etc/apt/keyrings",
    "/etc/apt/sources.list.d",
    "/etc/yum.repos.d",
    "/etc/pki/rpm-gpg",
    "/etc/sysctl.d",
    "/etc/modules-load.d",
)


@dataclass
class RunContext:
    system: SystemInfo
    executor: Executor = field(default_factory=Executor)
    workdir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="distroforge-")))
    on_output: OutputCallback | None = None

    def emit(self, line: str) -> None:
        if self.on_output is not None:
            self.on_output(line)

    async def run(self, command: Command) -> Result:
        return await self.executor.run(command, self.on_output)

    def tempfile(self, name: str) -> Path:
        path = self.workdir / name
        n = 1
        while path.exists():
            path = self.workdir / f"{n}-{name}"
            n += 1
        return path


class Operation(ABC):
    title: str
    needs_root: bool = False
    #: Non-empty when the user must explicitly acknowledge this operation.
    warning: str = ""

    @abstractmethod
    def preview(self) -> list[str]:
        """Human-readable lines describing exactly what will run."""

    @abstractmethod
    async def run(self, ctx: RunContext) -> Result: ...


class CommandOp(Operation):
    def __init__(self, title: str, command: Command, warning: str = "") -> None:
        self.title = title
        self.command = command
        self.needs_root = command.root
        self.warning = warning

    def preview(self) -> list[str]:
        return [self.command.display()]

    async def run(self, ctx: RunContext) -> Result:
        return await ctx.run(self.command)

    def __repr__(self) -> str:
        return f"CommandOp({self.title!r}, {self.command.display()!r})"


TaskFn = Callable[[RunContext], Awaitable[Result]]


class TaskOp(Operation):
    def __init__(
        self,
        title: str,
        fn: TaskFn,
        preview_lines: list[str],
        *,
        needs_root: bool = False,
        warning: str = "",
    ) -> None:
        self.title = title
        self._fn = fn
        self._preview = preview_lines
        self.needs_root = needs_root
        self.warning = warning

    def preview(self) -> list[str]:
        return list(self._preview)

    async def run(self, ctx: RunContext) -> Result:
        try:
            return await self._fn(ctx)
        except DownloadError as exc:
            return Result.failed(str(exc))
        except (OSError, ValueError) as exc:
            return Result.failed(f"{type(exc).__name__}: {exc}")

    def __repr__(self) -> str:
        return f"TaskOp({self.title!r})"


# ── Reusable operation builders ─────────────────────


def install_root_file(
    title: str,
    dest: str,
    *,
    content: str | None = None,
    url: str | None = None,
    mode: str = "0644",
) -> TaskOp:
    """Write ``content`` (or the file at ``url``) to ``dest`` as root.

    The data is staged in DistroForge's private temp dir and moved into place
    with ``install(1)``, avoiding the predictable ``/tmp`` paths used in v1.
    """
    check_path_within(dest, ROOT_WRITE_ROOTS)
    if (content is None) == (url is None):
        raise ValueError("Exactly one of content/url is required")
    source = f"download {url}" if url else "generated content"

    async def apply(ctx: RunContext) -> Result:
        staged = ctx.tempfile(Path(dest).name)
        if url is not None:
            ctx.emit(f"Downloading {url}")
            await asyncio.to_thread(download, url, staged, max_bytes=2 * 1024 * 1024)
        else:
            assert content is not None
            staged.write_text(content, encoding="utf-8")
        argv = ("install", "-D", "-m", mode, "-o", "root", "-g", "root", str(staged), dest)
        return await ctx.run(Command(argv, root=True))

    preview = [f"# {source} →", f"sudo install -D -m {mode} -o root -g root <staged> {dest}"]
    if content is not None:
        preview += [f"    {line}" for line in content.splitlines()]
    return TaskOp(title, apply, preview, needs_root=True)


def noop(title: str, message: str) -> TaskOp:
    async def apply(_: RunContext) -> Result:
        return Result(Status.SUCCESS, 0, message)

    return TaskOp(title, apply, [f"# {message}"])
