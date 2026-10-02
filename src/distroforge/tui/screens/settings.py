"""Settings: theme, install preferences, git identity."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch

from distroforge.core.settings import Settings, validate_git_name
from distroforge.core.validate import ValidationError, check_email
from distroforge.tui.themes import THEME_CHOICES

if TYPE_CHECKING:
    from distroforge.tui.app import DistroForgeApp


class SettingsScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    @property
    def df(self) -> DistroForgeApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        s = self.df.services.settings
        with VerticalScroll(classes="dialog dialog-wide", id="settings"):
            yield Label("Settings", classes="dialog-title")
            with Grid(id="settings-grid"):
                yield Label("Theme")
                yield Select(
                    [(label, name) for name, label in THEME_CHOICES],
                    value=self.app.theme,
                    allow_blank=False,
                    id="theme",
                )
                yield Label("Preferred source")
                yield Select(
                    [("Distro packages first", "native"), ("Flatpak first", "flatpak")],
                    value=s.prefer,
                    allow_blank=False,
                    id="prefer",
                )
                yield Label("Flatpak installs")
                yield Select(
                    [("Per user (no sudo)", "user"), ("System-wide", "system")],
                    value=s.flatpak_scope,
                    allow_blank=False,
                    id="scope",
                )
                yield Label("Skip installed items")
                yield Switch(value=s.skip_installed, id="skip")
                yield Label("Git name")
                yield Input(value=s.git_name, placeholder="Your Name", id="git-name")
                yield Label("Git email")
                yield Input(value=s.git_email, placeholder="you@example.com", id="git-email")
            yield Static("", id="settings-error", classes="error")
            yield Static(f"Stored in {self.df.services.paths.settings_file}", classes="muted")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="success")

    def on_mount(self) -> None:
        self._original_theme = self.app.theme

    @on(Select.Changed, "#theme")
    def _preview_theme(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            self.app.theme = event.value

    @on(Button.Pressed, "#save")
    def _save(self) -> None:
        name = self.query_one("#git-name", Input).value.strip()
        email = self.query_one("#git-email", Input).value.strip()
        try:
            validate_git_name(name)
            if email:
                check_email(email)
        except ValidationError as exc:
            self.query_one("#settings-error", Static).update(str(exc))
            return
        prefer = self.query_one("#prefer", Select).value
        scope = self.query_one("#scope", Select).value
        settings: Settings = replace(
            self.df.services.settings,
            theme=self.app.theme,
            prefer=str(prefer),
            flatpak_scope=str(scope),
            skip_installed=self.query_one("#skip", Switch).value,
            git_name=name,
            git_email=email,
        )
        self.df.services.update_settings(settings)
        self.notify("Settings saved")
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.app.theme = self._original_theme
        self.dismiss(False)
