from pathlib import Path

import pytest

from distroforge.core import shellrc


def test_upsert_is_idempotent() -> None:
    text = "alias ll='ls -l'\n"
    once = shellrc.upsert_block(text, "starship", ['eval "$(starship init zsh)"'])
    twice = shellrc.upsert_block(once, "starship", ['eval "$(starship init zsh)"'])
    assert once == twice
    assert once.startswith(text)
    assert once.count("distroforge:starship") == 2


def test_upsert_replaces_in_place() -> None:
    text = shellrc.upsert_block("a\n", "x", ["one"]) + "tail\n"
    updated = shellrc.upsert_block(text, "x", ["two"])
    assert "one" not in updated
    assert updated.endswith("tail\n")
    assert updated.index("two") < updated.index("tail")


def test_remove_restores_original() -> None:
    original = "export A=1\n"
    with_block = shellrc.upsert_block(original, "x", ["echo hi"])
    assert shellrc.remove_block(with_block, "x") == original
    assert shellrc.remove_block(original, "x") == original


def test_blocks_are_independent() -> None:
    text = shellrc.upsert_block("", "a", ["1"])
    text = shellrc.upsert_block(text, "b", ["2"])
    text = shellrc.upsert_block(text, "a", ["3"])
    assert shellrc.has_block(text, "b") and "2" in text and "1" not in text


@pytest.mark.parametrize("bad", ["Bad", "x y", "../x", ""])
def test_invalid_block_id(bad: str) -> None:
    with pytest.raises(ValueError):
        shellrc.render_block(bad, ["x"])


def test_multiline_injection_rejected() -> None:
    with pytest.raises(ValueError):
        shellrc.render_block("x", ["ok\n# <<< distroforge:x <<<\nrm -rf ~"])


def test_apply_block_preserves_mode_and_reports_change(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.write_text("# mine\n")
    rc.chmod(0o600)
    assert shellrc.apply_block(rc, "x", ["echo 1"]) is True
    assert shellrc.apply_block(rc, "x", ["echo 1"]) is False
    assert rc.stat().st_mode & 0o777 == 0o600
    assert shellrc.file_has_block(rc, "x", ["echo 1"])
    assert not shellrc.file_has_block(rc, "x", ["echo 2"])
    assert not list(tmp_path.glob(".*.tmp"))


def test_rc_file_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZDOTDIR", raising=False)
    assert shellrc.rc_file("bash", tmp_path, "x") == tmp_path / ".bashrc"
    assert shellrc.rc_file("zsh", tmp_path, "x") == tmp_path / ".zshrc"
    assert shellrc.rc_file("fish", tmp_path, "x") == tmp_path / ".config/fish/conf.d/distroforge-x.fish"
    monkeypatch.setenv("ZDOTDIR", str(tmp_path / "z"))
    assert shellrc.rc_file("zsh", tmp_path, "x") == tmp_path / "z" / ".zshrc"
    monkeypatch.setenv("ZDOTDIR", "relative")
    assert shellrc.rc_file("zsh", tmp_path, "x") == tmp_path / ".zshrc"


def test_symlinked_rc_file_stays_a_symlink(tmp_path: Path) -> None:
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    target = dotfiles / "zshrc"
    target.write_text("# managed by stow\n")
    link = tmp_path / ".zshrc"
    link.symlink_to(target)
    assert shellrc.apply_block(link, "starship", ["eval x"])
    assert link.is_symlink()
    assert "distroforge:starship" in target.read_text()
