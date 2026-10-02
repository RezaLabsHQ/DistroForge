"""Idempotent, reversible edits to shell startup files.

Instead of ``grep … || echo … >> ~/.zshrc`` (v1), every change is a named block::

    # >>> distroforge:starship >>>
    eval "$(starship init zsh)"
    # <<< distroforge:starship <<<

Re-applying replaces the block in place; removing it restores the file.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_BLOCK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SUPPORTED_SHELLS = ("bash", "zsh", "fish")


def _markers(block_id: str) -> tuple[str, str]:
    if not _BLOCK_ID.match(block_id):
        raise ValueError(f"Invalid block id: {block_id!r}")
    return f"# >>> distroforge:{block_id} >>>", f"# <<< distroforge:{block_id} <<<"


def _validate_lines(lines: list[str]) -> None:
    for line in lines:
        if any(ch in line for ch in "\n\r\0"):
            raise ValueError("Shell rc lines must be single lines")


def render_block(block_id: str, lines: list[str]) -> str:
    _validate_lines(lines)
    start, end = _markers(block_id)
    return "\n".join([start, *lines, end]) + "\n"


def _block_span(text: str, block_id: str) -> tuple[int, int] | None:
    start, end = _markers(block_id)
    match = re.search(rf"^{re.escape(start)}\n.*?^{re.escape(end)}\n?", text, flags=re.MULTILINE | re.DOTALL)
    return (match.start(), match.end()) if match else None


def has_block(text: str, block_id: str) -> bool:
    return _block_span(text, block_id) is not None


def upsert_block(text: str, block_id: str, lines: list[str]) -> str:
    block = render_block(block_id, lines)
    span = _block_span(text, block_id)
    if span:
        return text[: span[0]] + block + text[span[1] :]
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}\n{block}" if text else block


def remove_block(text: str, block_id: str) -> str:
    span = _block_span(text, block_id)
    if not span:
        return text
    before, after = text[: span[0]], text[span[1] :]
    if before.endswith("\n\n"):
        before = before[:-1]
    return before + after


def rc_file(shell: str, home: Path, block_id: str) -> Path:
    """Startup file for ``shell``. fish gets a dedicated conf.d snippet."""
    if shell == "bash":
        return home / ".bashrc"
    if shell == "zsh":
        zdotdir = os.environ.get("ZDOTDIR", "")
        return (Path(zdotdir) if zdotdir and Path(zdotdir).is_absolute() else home) / ".zshrc"
    if shell == "fish":
        return home / ".config" / "fish" / "conf.d" / f"distroforge-{block_id}.fish"
    raise ValueError(f"Unsupported shell: {shell}")


def atomic_write(path: Path, content: str) -> None:
    """Write via a temp file + rename, preserving the existing mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        Path(tmp).chmod(mode)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def apply_block(path: Path, block_id: str, lines: list[str]) -> bool:
    """Ensure ``path`` contains the block. Returns True if the file changed."""
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_block(current, block_id, lines)
    if updated == current:
        return False
    atomic_write(path, updated)
    return True


def file_has_block(path: Path, block_id: str, lines: list[str]) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return render_block(block_id, lines) in text
