import io
import tarfile
from pathlib import Path

import pytest

from distroforge.actions import REGISTRY, ActionContext, get_action
from distroforge.actions.user import _extract_fonts
from distroforge.backends import Backends
from distroforge.core.executor import Status
from distroforge.core.settings import Settings
from distroforge.core.system import Family
from distroforge.core.validate import ValidationError
from distroforge.engine.ops import CommandOp, RunContext, TaskOp

from ..conftest import make_system


def ctx_for(family: Family, tmp_path: Path, **settings: object) -> ActionContext:
    system = make_system(family, tmp_path)
    return ActionContext(system, Backends(system), Settings(**settings))  # type: ignore[arg-type]


def previews(ops: list) -> str:  # type: ignore[type-arg]
    return "\n".join(line for op in ops for line in op.preview())


def test_registry_names_unique_and_titled() -> None:
    assert len(REGISTRY) >= 15
    for name, action in REGISTRY.items():
        assert action.name == name and action.title


def test_unknown_param_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown parameter"):
        get_action("service").parse({"unit": "x.service", "evil": 1})


def test_apt_repo_ops(tmp_path: Path) -> None:
    action = get_action("apt_repo")
    params = action.parse(
        {
            "name": "docker",
            "key_url": "https://download.docker.com/linux/ubuntu/gpg",
            "keyring": "docker.asc",
            "url": "https://download.docker.com/linux/ubuntu",
            "suite": "noble",
            "components": ["stable"],
        }
    )
    text = previews(action.ops(params, ctx_for(Family.DEBIAN, tmp_path)))
    assert "/etc/apt/keyrings/docker.asc" in text
    assert "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" in text
    assert "/tmp/" not in text  # staged in a private dir, never a predictable /tmp path
    assert not action.supported(make_system(Family.FEDORA, tmp_path), params)


def test_dnf_repo_ops(tmp_path: Path) -> None:
    action = get_action("dnf_repo")
    params = action.parse(
        {
            "name": "vscode",
            "title": "Visual Studio Code",
            "baseurl": "https://packages.microsoft.com/yumrepos/vscode",
            "gpgkey": "https://packages.microsoft.com/keys/microsoft.asc",
        }
    )
    text = previews(action.ops(params, ctx_for(Family.FEDORA, tmp_path)))
    assert "/etc/yum.repos.d/distroforge-vscode.repo" in text
    assert "gpgcheck=1" in text


def test_rpmfusion_only_on_fedora_proper(tmp_path: Path) -> None:
    action = get_action("rpmfusion")
    params = action.parse({"nonfree": True})
    assert action.supported(make_system(Family.FEDORA, tmp_path), params)
    from distroforge.core.system import OsRelease

    rocky = make_system(Family.FEDORA, tmp_path, os=OsRelease(id="rocky", id_like=("rhel", "fedora")))
    assert not action.supported(rocky, params)
    ops = action.ops(params, ctx_for(Family.FEDORA, tmp_path))
    assert "rpmfusion-nonfree-release-44.noarch.rpm" in previews(ops)


def test_sysctl_writes_dropin_not_sysctl_conf(tmp_path: Path) -> None:
    action = get_action("sysctl")
    params = action.parse({"key": "vm.swappiness", "value": 10})
    text = previews(action.ops(params, ctx_for(Family.ARCH, tmp_path)))
    assert "/etc/sysctl.d/99-distroforge-vm-swappiness.conf" in text
    assert "vm.swappiness = 10" in text
    assert "/etc/sysctl.conf" not in text


@pytest.mark.parametrize(("family", "expected"), [(Family.FEDORA, "firewalld"), (Family.DEBIAN, "ufw"), (Family.ARCH, "ufw")])
def test_firewall_per_family(tmp_path: Path, family: Family, expected: str) -> None:
    action = get_action("firewall")
    assert expected in previews(action.ops({}, ctx_for(family, tmp_path)))


def test_user_group_uses_validated_username(tmp_path: Path) -> None:
    action = get_action("user_group")
    ops = action.ops(action.parse({"group": "docker", "create": True}), ctx_for(Family.FEDORA, tmp_path))
    assert [op.command.argv for op in ops if isinstance(op, CommandOp)] == [
        ("groupadd", "-f", "docker"),
        ("usermod", "-aG", "docker", "tester"),
    ]


async def test_shell_init_applies_only_to_installed_shells(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import distroforge.actions.user as user_mod

    monkeypatch.setattr(user_mod.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("bash", "zsh") else None)
    monkeypatch.delenv("ZDOTDIR", raising=False)
    ctx = ctx_for(Family.FEDORA, tmp_path)
    action = get_action("shell_init")
    params = action.parse({"id": "demo", "bash": ["echo b"], "zsh": ["echo z"], "fish": ["echo f"]})
    assert action.is_applied(params, ctx) is False
    [op] = action.ops(params, ctx)
    run = RunContext(system=ctx.system, workdir=tmp_path / "work")
    result = await op.run(run)
    assert result.status is Status.SUCCESS
    assert "echo b" in (tmp_path / ".bashrc").read_text()
    assert "echo z" in (tmp_path / ".zshrc").read_text()
    assert not (tmp_path / ".config/fish").exists()
    assert action.is_applied(params, ctx) is True
    again = await op.run(run)
    assert again.message == "Already configured"


def test_shell_init_requires_some_shell() -> None:
    with pytest.raises(ValidationError):
        get_action("shell_init").parse({"id": "x"})


async def test_git_identity_fails_clearly_without_settings(tmp_path: Path) -> None:
    ctx = ctx_for(Family.FEDORA, tmp_path)
    ops = get_action("git_identity").ops({}, ctx)
    assert isinstance(ops[0], TaskOp)
    result = await ops[0].run(RunContext(system=ctx.system, workdir=tmp_path))
    assert result.status is Status.FAILED and "Settings" in result.message


def test_git_identity_uses_settings(tmp_path: Path) -> None:
    ctx = ctx_for(Family.FEDORA, tmp_path, git_name="Ada Lovelace", git_email="ada@example.com")
    ops = get_action("git_identity").ops({"default_branch": "main"}, ctx)
    argv = [op.command.argv for op in ops if isinstance(op, CommandOp)]
    assert ("git", "config", "--global", "user.name", "Ada Lovelace") in argv
    assert ("git", "config", "--global", "user.email", "ada@example.com") in argv


def _tar_xz(members: dict[str, bytes], symlink: tuple[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if symlink:
            info = tarfile.TarInfo(symlink[0])
            info.type = tarfile.SYMTYPE
            info.linkname = symlink[1]
            tar.addfile(info)
    return buf.getvalue()


def test_font_extraction_cannot_escape(tmp_path: Path) -> None:
    archive = tmp_path / "f.tar.xz"
    archive.write_bytes(
        _tar_xz(
            {
                "Font-Regular.ttf": b"font",
                "../../evil.ttf": b"evil",
                "/abs/path.otf": b"abs",
                "README.md": b"readme",
                ".hidden.ttf": b"x",
            },
            symlink=("link.ttf", "/etc/passwd"),
        )
    )
    dest = tmp_path / "out"
    assert _extract_fonts(archive, dest) == 3
    assert sorted(p.name for p in dest.iterdir()) == ["Font-Regular.ttf", "evil.ttf", "path.otf"]
    assert not (tmp_path / "evil.ttf").exists()
    assert all(not p.is_symlink() for p in dest.iterdir())
