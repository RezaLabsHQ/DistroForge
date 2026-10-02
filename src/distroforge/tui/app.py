"""The DistroForge Textual application."""

from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from distroforge import __version__
from distroforge.core.settings import DEFAULT_THEME
from distroforge.services import Services
from distroforge.tui.screens.dialogs import HelpScreen
from distroforge.tui.screens.main import MainScreen
from distroforge.tui.themes import CUSTOM_THEMES, THEME_CHOICES, next_theme


class DistroForgeApp(App[None]):
    TITLE = "DistroForge"
    SUB_TITLE = f"v{__version__}"
    CSS_PATH = "distroforge.tcss"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark,f1", "help", "Help"),
        Binding("p", "profiles", "Profiles"),
        Binding("s", "settings", "Settings"),
        Binding("t", "cycle_theme", "Theme"),
    ]

    def __init__(self, services: Services, *, dry_run: bool = False) -> None:
        super().__init__()
        self.services = services
        self.dry_run_default = dry_run
        #: item id → backend override (None = automatic). Shared by every screen.
        self.selection: dict[str, str | None] = {}
        #: item id → installed? (filled by a background scan)
        self.installed: dict[str, bool] = {}
        self._persist_theme = False
        for theme in CUSTOM_THEMES:
            self.register_theme(theme)
        wanted = services.settings.theme
        self.theme = wanted if wanted in self.available_themes else DEFAULT_THEME

    def on_mount(self) -> None:
        self._persist_theme = True
        self.push_screen(MainScreen())
        for message in self.services.catalog.errors[:5]:
            self.notify(message, title="Catalog problem", severity="warning", timeout=10)

    def watch_theme(self, theme: str) -> None:
        # Persist theme changes (from `t`, the palette or Settings) across sessions.
        if self._persist_theme and theme != self.services.settings.theme and theme in dict(THEME_CHOICES):
            self.services.update_settings(replace(self.services.settings, theme=theme))

    def action_cycle_theme(self) -> None:
        self.theme = next_theme(self.theme)
        self.notify(dict(THEME_CHOICES).get(self.theme, self.theme), title="Theme", timeout=2)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_profiles(self) -> None:
        from distroforge.tui.screens.profiles import ProfilesScreen

        self.push_screen(ProfilesScreen())

    def action_settings(self) -> None:
        from distroforge.tui.screens.settings import SettingsScreen

        def saved(changed: bool | None) -> None:
            if changed and isinstance(self.screen, MainScreen):
                self.screen.rescan()

        self.push_screen(SettingsScreen(), saved)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Global shortcuts are disabled while a plan is running or a dialog is open.
        from distroforge.tui.screens.run import RunScreen

        if action in {"profiles", "settings"} and not isinstance(self.screen, MainScreen):
            return False
        running = isinstance(self.screen, RunScreen) and not self.screen.finished
        return not (action == "quit" and running)
