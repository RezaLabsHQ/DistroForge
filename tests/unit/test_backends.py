from pathlib import Path

import pytest

from distroforge.backends import BackendOptions, Backends
from distroforge.backends import native as native_mod
from distroforge.core.system import Family
from distroforge.core.validate import ValidationError
from distroforge.engine.ops import CommandOp

from ..conftest import make_system


def argvs(ops: list) -> list[list[str]]:  # type: ignore[type-arg]
    return [op.command.full_argv() for op in ops if isinstance(op, CommandOp)]


def test_apt_install_argv(tmp_path: Path) -> None:
    b = Backends(make_system(Family.DEBIAN, tmp_path)).get("apt")
    assert argvs(b.install_ops(["git", "curl"])) == [
        ["sudo", "-n", "--", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "git", "curl"]
    ]
    assert argvs(b.refresh_ops()) == [["sudo", "-n", "--", "apt-get", "update"]]


def test_dnf_install_argv(tmp_path: Path) -> None:
    b = Backends(make_system(Family.FEDORA, tmp_path)).get("dnf")
    assert argvs(b.install_ops(["git"])) == [["sudo", "-n", "--", "dnf", "install", "-y", "git"]]
    assert b.refresh_ops() == []


def test_pacman_never_partial_upgrade(tmp_path: Path) -> None:
    b = Backends(make_system(Family.ARCH, tmp_path)).get("pacman")
    assert argvs(b.refresh_ops()) == [["sudo", "-n", "--", "pacman", "-Syu", "--noconfirm"]]
    assert argvs(b.install_ops(["git"])) == [["sudo", "-n", "--", "pacman", "-S", "--needed", "--noconfirm", "git"]]


def test_aur_runs_as_user_and_warns(tmp_path: Path) -> None:
    backends = Backends(make_system(Family.ARCH, tmp_path, aur_helper="paru"))
    ops = backends.get("aur").install_ops(["visual-studio-code-bin"])
    assert argvs(ops) == [["paru", "-S", "--needed", "--noconfirm", "visual-studio-code-bin"]]
    assert ops[0].warning
    assert not Backends(make_system(Family.ARCH, tmp_path)).supported("aur")


@pytest.mark.parametrize(("scope", "flag", "root"), [("user", "--user", False), ("system", "--system", True)])
def test_flatpak_scope(tmp_path: Path, scope: str, flag: str, root: bool) -> None:
    backends = Backends(make_system(Family.FEDORA, tmp_path), BackendOptions(flatpak_scope=scope))
    op = backends.flatpak.install_ops(["org.gimp.GIMP"])[0]
    assert isinstance(op, CommandOp)
    assert op.command.root is root
    assert op.command.argv == ("flatpak", "install", flag, "-y", "--noninteractive", "flathub", "org.gimp.GIMP")


def test_backends_supported_only_for_own_family(tmp_path: Path) -> None:
    backends = Backends(make_system(Family.FEDORA, tmp_path))
    assert backends.supported("dnf") and backends.supported("flatpak")
    assert not backends.supported("apt") and not backends.supported("pacman")
    assert not backends.supported("snap")


def test_install_rejects_option_injection(tmp_path: Path) -> None:
    b = Backends(make_system(Family.DEBIAN, tmp_path)).get("apt")
    with pytest.raises(ValidationError):
        b.install_ops(["--allow-unauthenticated"])


def test_apt_snapshot_parses_dpkg_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = "ii  git\nrc  removed-pkg\nii  curl\nun  never\n"
    monkeypatch.setattr(native_mod, "probe", lambda argv, **kw: (0, out))
    b = Backends(make_system(Family.DEBIAN, tmp_path)).get("apt")
    monkeypatch.setattr(b, "ready", lambda: True)
    assert b.installed_set() == {"git", "curl"}
    assert b.is_installed(["git", "curl"])
    assert not b.is_installed(["git", "removed-pkg"])
    assert not b.is_installed([])


def test_dnf_resolves_virtual_provides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_probe(argv: list[str], **_: object) -> tuple[int, str]:
        if argv[:2] == ["rpm", "-qa"]:
            return 0, "nodejs\nnodejs-npm\n"
        if argv[:3] == ["rpm", "-q", "--whatprovides"]:
            return (0, "nodejs-npm") if argv[3] == "npm" else (1, "")
        raise AssertionError(argv)

    monkeypatch.setattr(native_mod, "probe", fake_probe)
    b = Backends(make_system(Family.FEDORA, tmp_path)).get("dnf")
    monkeypatch.setattr(b, "ready", lambda: True)
    assert b.is_installed(["nodejs", "npm"])
    assert not b.is_installed(["nodejs", "yarn"])


def test_cache_invalidation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_probe(argv: list[str], **_: object) -> tuple[int, str]:
        calls.append(argv)
        return 0, "git\n"

    monkeypatch.setattr(native_mod, "probe", fake_probe)
    backends = Backends(make_system(Family.ARCH, tmp_path))
    b = backends.get("pacman")
    monkeypatch.setattr(b, "ready", lambda: True)
    b.installed_set()
    b.installed_set()
    assert len(calls) == 1
    backends.invalidate()
    b.installed_set()
    assert len(calls) == 2
