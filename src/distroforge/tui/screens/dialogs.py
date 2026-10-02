"""Modal dialogs: confirm, failure decision, help/about."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from distroforge import __url__, __version__
from distroforge.core.executor import Result
from distroforge.engine.planner import Step
from distroforge.engine.runner import Decision
from distroforge.tui.widgets.logo import Logo


class ConfirmDialog(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", "Cancel", show=False)]

    def __init__(self, title: str, message: str, *, confirm: str = "Yes", danger: bool = False) -> None:
        super().__init__()
        self._title, self._message, self._confirm, self._danger = title, message, confirm, danger

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title, classes="dialog-title")
            yield Static(self._message, classes="dialog-body")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="no")
                yield Button(self._confirm, id="yes", variant="error" if self._danger else "primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class FailureDialog(ModalScreen[Decision]):
    """Asked when a step fails: retry it, skip the affected items, or stop."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "decide('retry')", "Retry"),
        Binding("s", "decide('skip')", "Skip"),
        Binding("a", "decide('abort')", "Abort"),
        Binding("escape", "decide('skip')", "Skip", show=False),
    ]

    def __init__(self, step: Step, result: Result) -> None:
        super().__init__()
        self._step, self._result = step, result

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog dialog-wide"):
            yield Label(f"✗ {self._step.title}", classes="dialog-title error")
            yield Static(self._result.message or "The step failed.", classes="dialog-body")
            if self._result.output_tail:
                with VerticalScroll(classes="dialog-output"):
                    yield Static(Text(self._result.output_tail))
            with Horizontal(classes="dialog-buttons"):
                yield Button("Retry  [r]", id="retry", variant="primary")
                yield Button("Skip  [s]", id="skip")
                yield Button("Abort  [a]", id="abort", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_decide(event.button.id or "skip")

    def action_decide(self, choice: str) -> None:
        self.dismiss(Decision(choice))


HELP_KEYS = (
    ("Space / Enter", "select or deselect the highlighted item"),
    ("m", "cycle install method (native / Flatpak / AUR / script)"),
    ("/", "search the whole catalog"),
    ("a / n", "select all / none in the current list"),
    ("r", "review the plan and install"),
    ("p", "profiles — load, merge, save and share selections"),
    ("s", "settings — theme, git identity, preferences"),
    ("t", "cycle themes (Catppuccin, Forge, Nord, …)"),
    ("Ctrl+P", "command palette"),
    ("Tab", "move between panels"),
    ("q", "quit"),
)


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape,q,question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog dialog-wide", id="help"):
            yield Logo(tagline=f"v{__version__} · Forge your Linux setup")
            keys = Text()
            for key, desc in HELP_KEYS:
                keys.append(f"  {key:<14}", style="bold")
                keys.append(f"{desc}\n")
            yield Static(keys, classes="help-keys")
            yield Static(
                "Add your own apps: drop YAML files into ~/.config/distroforge/catalog.d/\n"
                f"Docs & issues: {__url__}\n"
                "Made by Hamid Alami at Reza Labs HQ · MIT licensed",
                classes="dialog-body muted",
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss()
