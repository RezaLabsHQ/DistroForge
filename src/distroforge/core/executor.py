"""Command execution.

Security invariant: commands are argv tuples executed with
``subprocess.Popen`` / ``subprocess.run`` and **never** through a shell,
so catalog data can never be interpreted as shell syntax.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from distroforge.core.logging import get_logger

log = get_logger("exec")

OutputCallback = Callable[[str], None]

_TAIL_LINES = 40
_CHUNK = 64 * 1024
_MAX_LINE = 64 * 1024  # longer "lines" are emitted in pieces
_DRAIN_SECONDS = 2.0  # how long to keep reading output after the process exits


class Status(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def ok(self) -> bool:
        return self in (Status.SUCCESS, Status.SKIPPED)


@dataclass(frozen=True)
class Result:
    status: Status
    returncode: int | None = None
    message: str = ""
    output_tail: str = ""
    duration: float = 0.0

    @classmethod
    def success(cls, message: str = "") -> Result:
        return cls(Status.SUCCESS, 0, message)

    @classmethod
    def failed(cls, message: str, returncode: int | None = None, tail: str = "") -> Result:
        return cls(Status.FAILED, returncode, message, tail)

    @classmethod
    def skipped(cls, message: str = "") -> Result:
        return cls(Status.SKIPPED, None, message)


@dataclass(frozen=True)
class Command:
    """An argv to execute, optionally as root via ``sudo -n``.

    ``-n`` (non-interactive) guarantees a command can never block on a password
    prompt hidden behind the TUI; credentials are validated up-front instead.
    """

    argv: tuple[str, ...]
    root: bool = False
    env: Mapping[str, str] = field(default_factory=dict)
    timeout: float = 3600.0
    ok_codes: frozenset[int] = frozenset({0})

    def __post_init__(self) -> None:
        # Empty *arguments* are legitimate (e.g. ssh-keygen -N ""); an empty program is not.
        if not self.argv or not self.argv[0] or not all(isinstance(a, str) for a in self.argv):
            raise ValueError(f"Invalid argv: {self.argv!r}")
        if any("\0" in a for a in self.argv):
            raise ValueError("NUL byte in argv")

    def full_argv(self) -> list[str]:
        if not self.root:
            return list(self.argv)
        # sudo resets the environment, so variables are passed through env(1).
        env_args = [f"{k}={v}" for k, v in sorted(self.env.items())]
        prefix = ["sudo", "-n", "--"]
        return [*prefix, "env", *env_args, *self.argv] if env_args else [*prefix, *self.argv]

    def display(self) -> str:
        if self.root:
            return shlex.join(self.full_argv()).replace("sudo -n -- ", "sudo ", 1)
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in sorted(self.env.items()))
        return f"{env} {shlex.join(self.argv)}".strip()


class Executor:
    """Runs :class:`Command` objects, streaming merged stdout/stderr line by line."""

    async def run(self, command: Command, on_output: OutputCallback | None = None) -> Result:
        argv = command.full_argv()
        log.info("RUN %s", command.display())
        if not shutil.which(argv[0]):
            return Result.failed(f"'{argv[0]}' not found on PATH", returncode=127)

        env = None
        if command.env and not command.root:
            env = {**os.environ, **command.env}

        start = time.monotonic()
        tail: deque[str] = deque(maxlen=_TAIL_LINES)
        loop = asyncio.get_running_loop()
        finished = threading.Event()

        def deliver(line: str) -> None:  # runs on the event loop
            if finished.is_set():
                return  # late output from a lingering background process
            tail.append(line)
            log.debug("  | %s", line)
            if on_output is not None:
                on_output(line)

        try:
            proc = await asyncio.to_thread(
                subprocess.Popen,
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except OSError as exc:
            return Result.failed(f"Could not start: {exc}", returncode=126)

        assert proc.stdout is not None
        fd = proc.stdout.fileno()

        def read_output() -> None:  # runs in a reader thread
            # Raw chunks rather than lines: progress bars use bare \r, and a single
            # huge "line" must never raise or stall the reader.
            buffer = b""

            def send(raw: bytes) -> None:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    loop.call_soon_threadsafe(deliver, line)

            try:
                while chunk := os.read(fd, _CHUNK):
                    buffer += chunk.replace(b"\r", b"\n")
                    *lines, buffer = buffer.split(b"\n")
                    for raw in lines:
                        send(raw)
                    while len(buffer) > _MAX_LINE:
                        send(buffer[:_MAX_LINE])
                        buffer = buffer[_MAX_LINE:]
                send(buffer)
            except (OSError, RuntimeError):  # pipe closed / loop shut down
                pass

        reader = threading.Thread(target=read_output, name="distroforge-output", daemon=True)
        reader.start()
        try:
            # Completion is the process exiting, not stdout EOF: a daemon started by a
            # post-install script may keep the pipe open long after we are done.
            # (asyncio's Process.wait() waits for the pipes on Python < 3.13, so the
            # wait happens in a thread on Popen instead.)
            returncode = await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=command.timeout)
        except asyncio.TimeoutError:
            await _terminate(proc)
            finished.set()
            return Result.failed(f"Timed out after {command.timeout:.0f}s", tail="\n".join(tail))
        except asyncio.CancelledError:
            await _terminate(proc)
            finished.set()
            raise

        await asyncio.to_thread(reader.join, _DRAIN_SECONDS)
        await asyncio.sleep(0)  # let already-queued output callbacks run
        finished.set()
        if reader.is_alive():
            log.debug("Output still open after exit (background process?); stopped reading")
        else:
            proc.stdout.close()

        duration = time.monotonic() - start
        output = "\n".join(tail)
        if returncode in command.ok_codes:
            log.info("OK  (%.1fs) exit=%s", duration, returncode)
            return Result(Status.SUCCESS, returncode, "", output, duration)
        log.warning("ERR (%.1fs) exit=%s", duration, returncode)
        return Result(Status.FAILED, returncode, f"Exited with code {returncode}", output, duration)


async def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        await asyncio.to_thread(proc.wait, 10)
    except subprocess.TimeoutExpired:
        proc.kill()
        await asyncio.to_thread(proc.wait)


def probe(argv: list[str], timeout: float = 30.0) -> tuple[int, str]:
    """Run a read-only query synchronously. Returns ``(returncode, stdout)``.

    Used for "is it installed?" style checks; never escalates privileges.
    """
    if not argv or not shutil.which(argv[0]):
        return 127, ""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("probe %s failed: %s", argv, exc)
        return 1, ""
    return proc.returncode, proc.stdout
