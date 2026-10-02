import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from distroforge.core import privilege
from distroforge.core.logging import get_logger, redact, setup_logging


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("GITHUB_TOKEN=ghp_abcdef123", "ghp_abcdef123"),
        ("export API_KEY: sk-live-999", "sk-live-999"),
        ("db_password=hunter2", "hunter2"),
        ("Authorization: Bearer eyJhbGciOi", "eyJhbGciOi"),
    ],
)
def test_redact_masks_secrets(raw: str, secret: str) -> None:
    masked = redact(raw)
    assert secret not in masked and "***" in masked


def test_redact_leaves_normal_text() -> None:
    line = "sudo apt-get install -y git curl"
    assert redact(line) == line


def test_log_file_is_private_redacted_and_pruned(tmp_path: Path) -> None:
    for i in range(3):
        (tmp_path / f"distroforge-2020010{i}-000000.log").write_text("old")
    log_file = setup_logging(tmp_path, keep=2)
    assert log_file.stat().st_mode & 0o777 == 0o600
    get_logger("test").info("using MY_SECRET=topsecret for %s", "x")
    for handler in get_logger().handlers:
        handler.flush()
    content = log_file.read_text()
    assert "topsecret" not in content and "MY_SECRET=***" in content
    assert len(list(tmp_path.glob("distroforge-*.log"))) == 2


class _Proc:
    def __init__(self, code: int) -> None:
        self.returncode = code


def test_credentials_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(privilege.shutil, "which", lambda _: "/usr/bin/sudo")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: Any) -> _Proc:
        calls.append(argv)
        return _Proc(0)

    monkeypatch.setattr(privilege.subprocess, "run", fake_run)
    assert privilege.credentials_cached()
    assert calls == [["sudo", "-n", "-v"]]  # never prompts


def test_authenticate_prompts_only_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(privilege.shutil, "which", lambda _: "/usr/bin/sudo")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: Any) -> _Proc:
        calls.append(argv)
        return _Proc(1 if argv == ["sudo", "-n", "-v"] else 0)

    monkeypatch.setattr(privilege.subprocess, "run", fake_run)
    assert privilege.authenticate_interactive()
    assert calls == [["sudo", "-n", "-v"], ["sudo", "-v"]]


def test_authenticate_handles_failure_and_missing_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(privilege.shutil, "which", lambda _: None)
    assert not privilege.sudo_available()
    assert not privilege.authenticate_interactive()
    assert not privilege.credentials_cached()

    monkeypatch.setattr(privilege.shutil, "which", lambda _: "/usr/bin/sudo")

    def boom(argv: list[str], **_: Any) -> _Proc:
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(privilege.subprocess, "run", boom)
    assert not privilege.credentials_cached()
    assert not privilege.authenticate_interactive()


async def test_keepalive_refreshes_until_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    class FakeProc:
        async def wait(self) -> int:
            return 0

    async def fake_exec(*argv: str, **_: Any) -> FakeProc:
        calls.append(argv)
        return FakeProc()

    monkeypatch.setattr(privilege.asyncio, "create_subprocess_exec", fake_exec)
    task = asyncio.create_task(privilege.keepalive(interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls and all(c == ("sudo", "-n", "-v") for c in calls)
