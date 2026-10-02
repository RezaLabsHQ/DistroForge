"""Profiles: load, merge, save and delete named selections."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from distroforge.core.validate import ValidationError
from distroforge.engine.profiles import Profile, delete_profile, load_profiles, save_profile

if TYPE_CHECKING:
    from distroforge.tui.app import DistroForgeApp


class ProfilesScreen(ModalScreen[bool]):
    """Dismisses with True if the selection changed."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self) -> None:
        super().__init__()
        self.profiles: list[Profile] = []
        self.changed = False

    @property
    def df(self) -> DistroForgeApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog dialog-wide", id="profiles"):
            yield Label("Profiles", classes="dialog-title")
            yield Static(
                "Profiles are starting points — load one, then add or remove anything you like.",
                classes="muted",
            )
            with Horizontal(id="profiles-body"):
                yield OptionList(id="profile-list")
                yield Static(id="profile-info")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Replace selection", id="load", variant="primary")
                yield Button("Add to selection", id="merge")
                yield Button("Delete", id="delete", variant="error")
            yield Label("Save the current selection as a profile:", classes="section")
            with Horizontal(classes="dialog-buttons"):
                yield Input(placeholder="Profile name, e.g. “Work laptop”", id="profile-name")
                yield Button("Save", id="save", variant="success")
            yield Static(f"Saved to {self.df.services.paths.profiles_dir}", classes="muted")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="close")

    def on_mount(self) -> None:
        self._reload()

    def _reload(self, highlight: str | None = None) -> None:
        self.profiles = load_profiles(self.df.services.paths.profiles_dir)
        options = []
        for profile in self.profiles:
            label = Text(profile.name)
            label.append("  built-in" if profile.builtin else "  yours", style="dim")
            options.append(Option(label, id=profile.id if profile.builtin else f"user:{profile.id}"))
        option_list = self.query_one("#profile-list", OptionList)
        option_list.set_options(options)
        index = next((i for i, p in enumerate(self.profiles) if p.id == highlight), 0)
        if self.profiles:
            option_list.highlighted = index
        self._show_info()

    def _current(self) -> Profile | None:
        index = self.query_one("#profile-list", OptionList).highlighted
        return self.profiles[index] if index is not None and index < len(self.profiles) else None

    @on(OptionList.OptionHighlighted, "#profile-list")
    def _show_info(self) -> None:
        profile = self._current()
        info = self.query_one("#profile-info", Static)
        delete = self.query_one("#delete", Button)
        if profile is None:
            info.update("")
            delete.disabled = True
            return
        selection, unknown = profile.selection(self.df.services.catalog)
        catalog = self.df.services.catalog
        text = Text()
        text.append(profile.name + "\n", style="bold")
        if profile.description:
            text.append(profile.description + "\n\n", style="italic")
        text.append(", ".join(catalog.items[i].name for i in selection))
        if unknown:
            text.append(f"\n\nUnknown here (ignored): {', '.join(unknown)}", style="dim")
        info.update(text)
        delete.disabled = profile.builtin

    def _apply(self, *, replace: bool) -> None:
        profile = self._current()
        if profile is None:
            return
        selection, unknown = profile.selection(self.df.services.catalog)
        resolver = self.df.services.resolver()
        catalog = self.df.services.catalog
        usable = {k: v for k, v in selection.items() if resolver.supported(catalog.items[k])}
        if replace:
            self.df.selection.clear()
        self.df.selection.update(usable)
        self.changed = True
        skipped = len(selection) - len(usable) + len(unknown)
        note = f" ({skipped} not available on this system)" if skipped else ""
        self.notify(f"{'Loaded' if replace else 'Added'} “{profile.name}”: {len(usable)} items{note}")
        self.dismiss(True)

    @on(Button.Pressed, "#load")
    def _load(self) -> None:
        self._apply(replace=True)

    @on(Button.Pressed, "#merge")
    def _merge(self) -> None:
        self._apply(replace=False)

    @on(Button.Pressed, "#delete")
    def _delete(self) -> None:
        profile = self._current()
        if profile is None or profile.builtin:
            return
        delete_profile(profile)
        self.notify(f"Deleted “{profile.name}”")
        self._reload()

    @on(Button.Pressed, "#save")
    @on(Input.Submitted, "#profile-name")
    def _save(self) -> None:
        name = self.query_one("#profile-name", Input).value.strip()
        if not name:
            self.notify("Give the profile a name.", severity="warning")
            return
        if not self.df.selection:
            self.notify("Nothing is selected.", severity="warning")
            return
        try:
            path = save_profile(self.df.services.paths.profiles_dir, name, dict(self.df.selection))
        except (ValidationError, OSError) as exc:
            self.notify(str(exc), severity="error")
            return
        self.notify(f"Saved {path}")
        self.query_one("#profile-name", Input).value = ""
        self._reload(highlight=path.stem)

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(self.changed)
