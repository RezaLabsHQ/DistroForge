from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from distroforge import cli
from distroforge.catalog import Catalog
from distroforge.core.paths import AppPaths
from distroforge.core.system import Family
from distroforge.services import Services


@pytest.fixture
def services(tmp_path: Path, catalog: Catalog, make_env, monkeypatch: pytest.MonkeyPatch) -> Services:  # type: ignore[no-untyped-def]
    env = make_env(Family.DEBIAN, installed={"git"})
    root = tmp_path / "xdg"
    paths = AppPaths(root / "c", root / "d", root / "s", root / "k")
    paths.ensure()
    svc = Services(paths, env.settings, env.system, catalog, env.backends, root / "log")
    monkeypatch.setattr(cli, "bootstrap", lambda family=None: svc)
    return svc


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out + out.err


def test_list(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "list", "--category", "media")
    assert code == 0
    assert "vlc" in out and "gimp" not in out


def test_list_unknown_category(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "list", "--category", "nope")[0] == cli.EXIT_USAGE


def test_apply_dry_run_shows_commands_and_changes_nothing(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = run(capsys, "apply", "jq", "git", "--dry-run")
    assert code == 0
    assert "apt-get update" in out
    assert "apt-get install -y jq" in out
    assert "Git — already installed" in out
    assert "Previewed:" in out


def test_apply_profile_and_method_override(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "apply", "--profile", "creator", "--method", "vlc=flatpak", "--dry-run")
    assert code == 0
    assert "org.videolan.VLC" in out


def test_apply_profile_file(services: Services, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    profile = tmp_path / "mine.yaml"
    profile.write_text("name: Mine\nitems: [jq, not-a-real-item]\n")
    code, out = run(capsys, "apply", "--profile", str(profile), "--dry-run")
    assert code == 0
    assert "not-a-real-item" in out and "jq" in out


@pytest.mark.parametrize(
    "argv",
    [
        ("apply",),
        ("apply", "nope"),
        ("apply", "--profile", "nope"),
        ("apply", "jq", "--method", "garbage"),
    ],
)
def test_apply_usage_errors(
    services: Services, capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    assert run(capsys, *argv)[0] == cli.EXIT_USAGE


def test_apply_refuses_root(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    services.system = replace(services.system, is_root=True)
    code, out = run(capsys, "apply", "jq", "--yes")
    assert code == cli.EXIT_USAGE and "root" in out


def test_apply_needs_confirmation_without_tty(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "apply", "jq")
    assert code == cli.EXIT_USAGE and "--yes" in out


def test_nothing_to_do(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "apply", "git")
    assert code == 0 and "Nothing to do" in out


def test_profiles_and_doctor(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "profiles")
    assert code == 0 and "developer" in out
    code, out = run(capsys, "doctor")
    assert code == 0 and "Debian / Ubuntu" in out


def test_tui_requires_terminal(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "tui")
    assert code == cli.EXIT_USAGE and "terminal" in out


def test_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good.yaml"
    good.write_text(
        "items:\n  - {id: my-app, name: My App, category: utilities, install: [{flatpak: com.example.App}]}\n"
    )
    code, out = run(capsys, "validate", str(good))
    assert code == 0 and "1 item" in out

    bad = tmp_path / "bad.yaml"
    bad.write_text("items:\n  - {id: evil, name: Evil, category: utilities, install: [{apt: '$(reboot)'}]}\n")
    code, out = run(capsys, "validate", str(bad))
    assert code == cli.EXIT_FAILED and "Invalid package" in out

    assert run(capsys, "validate", str(tmp_path / "missing.yaml"))[0] == cli.EXIT_USAGE


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "2.0.0" in capsys.readouterr().out


def test_integrate_install_and_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import configparser
    import shutil
    import subprocess

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    exe = tmp_path / "my bin" / "distroforge"
    code, _ = run(capsys, "integrate", "--exec", str(exe))
    assert code == 0
    desktop = tmp_path / "data/applications/distroforge.desktop"
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string(desktop.read_text())
    entry = parser["Desktop Entry"]
    assert entry["Terminal"] == "true"
    assert entry["Exec"] == f'"{exe}" tui'
    assert entry["Icon"] == "distroforge"
    assert (tmp_path / "data/icons/hicolor/scalable/apps/distroforge.svg").read_text().startswith("<svg")
    assert (tmp_path / "data/bash-completion/completions/distroforge").exists()
    assert (tmp_path / "data/zsh/site-functions/_distroforge").exists()
    assert (tmp_path / "config/fish/completions/distroforge.fish").exists()
    if shutil.which("desktop-file-validate"):
        result = subprocess.run(["desktop-file-validate", str(desktop)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    code, _ = run(capsys, "integrate", "--remove")
    assert code == 0 and not desktop.exists()


def test_list_ids_is_machine_readable(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "list", "--ids")
    assert code == 0
    ids = out.split()
    assert set(ids) == set(services.catalog.items)
    assert "python-build-deps" in ids
