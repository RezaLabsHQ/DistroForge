"""The DistroForge mark: an anvil throwing a spark, coloured from the active theme."""

from __future__ import annotations

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.widgets import Static

from distroforge.tui.colors import colour

ANVIL = (
    "            ✦            ",
    "        ╲   ┃   ╱        ",
    "  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄  ",
    "  ▀██████████████████▀▀▀▄",
    "     ▀▀███████████▀▀     ",
    "          █████          ",
    "        ▄███████▄        ",
    "       ▀▀▀▀▀▀▀▀▀▀▀       ",
)

WORDMARK = (
    "█▀▄ █ █▀ ▀█▀ █▀█ █▀█ █▀▀ █▀█ █▀█ █▀▀ █▀▀",
    "█▄▀ █ ▄█  █  █▀▄ █▄█ █▀  █▄█ █▀▄ █▄█ ██▄",
)


def _blend(a: str, b: str, t: float) -> str:
    ca, cb = Color.parse(a).get_truecolor(), Color.parse(b).get_truecolor()
    mix = [round(x + (y - x) * t) for x, y in zip(ca, cb, strict=True)]
    return f"#{mix[0]:02x}{mix[1]:02x}{mix[2]:02x}"


def render_logo(top: str, bottom: str, *, wordmark: bool = True, tagline: str = "") -> Text:
    """Vertical gradient from ``top`` (spark) to ``bottom`` (anvil base)."""
    lines = list(ANVIL)
    text = Text(justify="center")
    for i, line in enumerate(lines):
        colour = _blend(top, bottom, i / max(1, len(lines) - 1))
        text.append(line + "\n", Style(color=colour, bold=True))
    if wordmark:
        text.append("\n")
        for line in WORDMARK:
            text.append(line + "\n", Style(color=top, bold=True))
    if tagline:
        text.append("\n" + tagline, Style(dim=True))
    return text


class Logo(Static):
    """Theme-aware logo. Re-renders when the app theme changes."""

    DEFAULT_CSS = "Logo { width: auto; height: auto; content-align: center middle; }"

    def __init__(self, *, wordmark: bool = True, tagline: str = "", id: str | None = None) -> None:
        super().__init__(id=id)
        self._wordmark = wordmark
        self._tagline = tagline

    def on_mount(self) -> None:
        self.refresh_logo()
        self.watch(self.app, "theme", lambda _old, _new=None: self.refresh_logo(), init=False)

    def refresh_logo(self) -> None:
        self.update(
            render_logo(
                colour(self.app, "accent"),
                colour(self.app, "primary"),
                wordmark=self._wordmark,
                tagline=self._tagline,
            )
        )
