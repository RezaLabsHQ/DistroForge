import hashlib
import io
from pathlib import Path
from typing import Any

import pytest

from distroforge.core import net
from distroforge.core.executor import Result, Status
from distroforge.core.system import Family
from distroforge.core.validate import ValidationError
from distroforge.engine.ops import RunContext, install_root_file

from ..conftest import make_system


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def fake_opener(payload: bytes) -> Any:
    class Opener:
        def open(self, request: Any, timeout: float) -> FakeResponse:
            return FakeResponse(payload)

    return Opener()


def test_download_verifies_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(net, "_opener", fake_opener(b"hello"))
    good = hashlib.sha256(b"hello").hexdigest()
    dest = tmp_path / "ok"
    assert net.download("https://example.com/x", dest, sha256=good) == good
    assert dest.read_bytes() == b"hello"
    assert dest.stat().st_mode & 0o777 == 0o600

    bad = tmp_path / "bad"
    with pytest.raises(net.DownloadError, match="Checksum mismatch"):
        net.download("https://example.com/x", bad, sha256="0" * 64)
    assert not bad.exists()


def test_download_enforces_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(net, "_opener", fake_opener(b"x" * 2048))
    dest = tmp_path / "big"
    with pytest.raises(net.DownloadError, match="larger"):
        net.download("https://example.com/x", dest, max_bytes=1024)
    assert not dest.exists()


def test_download_rejects_http_and_existing_files(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        net.download("http://example.com/x", tmp_path / "x")
    existing = tmp_path / "exists"
    existing.write_text("keep")
    with pytest.raises(FileExistsError):
        net.download("https://example.com/x", existing)
    assert existing.read_text() == "keep"


def test_redirect_to_http_refused() -> None:
    handler = net._HttpsOnlyRedirects()
    with pytest.raises(net.DownloadError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://evil.example/x")


def test_install_root_file_confined_to_allowlist() -> None:
    with pytest.raises(ValidationError):
        install_root_file("x", "/etc/passwd", content="pwned")
    with pytest.raises(ValidationError):
        install_root_file("x", "/etc/sysctl.d/../shadow", content="x")


async def test_install_root_file_stages_privately(tmp_path: Path) -> None:
    calls = []

    class FakeExecutor:
        async def run(self, command, on_output=None):  # type: ignore[no-untyped-def]
            calls.append(command)
            return Result(Status.SUCCESS, 0)

    ctx = RunContext(system=make_system(Family.FEDORA, tmp_path), executor=FakeExecutor(), workdir=tmp_path)  # type: ignore[arg-type]
    op = install_root_file("sysctl", "/etc/sysctl.d/99-x.conf", content="vm.swappiness = 10\n")
    result = await op.run(ctx)
    assert result.status is Status.SUCCESS
    [cmd] = calls
    assert cmd.root
    assert cmd.argv[:9] == ("install", "-D", "-m", "0644", "-o", "root", "-g", "root", str(tmp_path / "99-x.conf"))
    assert cmd.argv[-1] == "/etc/sysctl.d/99-x.conf"
    assert (tmp_path / "99-x.conf").read_text() == "vm.swappiness = 10\n"
