"""End-to-end UI tests driven by Textual's Pilot on a fake, fully stubbed system."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from textual.widgets import Button, DataTable, Input, Select

from distroforge.catalog import Catalog
from distroforge.core.executor import Result
from distroforge.core.paths import AppPaths
from distroforge.core.settings import Settings, load_settings
from distroforge.core.system import Family
from distroforge.engine.ops import Operation, RunContext
from distroforge.engine.planner import ItemPlan, Plan, Step
from distroforge.engine.runner import ItemStatus
from distroforge.services import Services
from distroforge.tui.app import DistroForgeApp
from distroforge.tui.screens.dialogs import FailureDialog, HelpScreen
from distroforge.tui.screens.main import MainScreen
from distroforge.tui.screens.profiles import ProfilesScreen
from distroforge.tui.screens.review import ReviewScreen
from distroforge.tui.screens.run import RunScreen
from distroforge.tui.screens.settings import SettingsScreen
from distroforge.tui.themes import THEME_NAMES

SIZE = (160, 48)


@pytest.fixture
def make_app(tmp_path: Path, catalog: Catalog, make_env) -> Callable[..., DistroForgeApp]:  # type: ignore[no-untyped-def]
    def factory(
        *, installed: set[str] | None = None, dry_run: bool = True, **settings: object
    ) -> DistroForgeApp:
        env = make_env(Family.FEDORA, installed=installed or set(), settings=Settings(**settings))  # type: ignore[arg-type]
        root = tmp_path / "xdg"
        paths = AppPaths(root / "config", root / "data", root / "state", root / "cache")
        paths.ensure()
        services = Services(paths, env.settings, env.system, catalog, env.backends, root / "test.log")
        return DistroForgeApp(services, dry_run=dry_run)

    return factory


def visible_ids(app: DistroForgeApp) -> list[str]:
    assert isinstance(app.screen, MainScreen)
    return [item.id for item in app.screen._visible]


async def search(pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    await pilot.press("slash", *text, "enter")
    await pilot.pause()


async def test_main_screen_lists_catalog_and_scans_state(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app(installed={"git"})
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.5)
        assert isinstance(app.screen, MainScreen)
        assert len(visible_ids(app)) == len(app.services.catalog.items)
        assert app.installed["git"] is True
        assert app.installed["jq"] is False


async def test_search_select_and_cycle_method(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await search(pilot, "vlc")
        assert visible_ids(app) == ["vlc"]
        await pilot.press("space")
        assert app.selection == {"vlc": None}
        await pilot.press("m")
        assert app.selection == {"vlc": "flatpak"}
        await pilot.press("m")
        assert app.selection == {"vlc": "dnf"}
        await pilot.press("space")
        assert app.selection == {}


async def test_unsupported_item_cannot_be_selected(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await search(pilot, "ghostty")
        await pilot.press("space")
        await pilot.pause()
        assert app.selection == {}


async def test_select_all_in_category_and_selected_view(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await search(pilot, "font")
        fonts = visible_ids(app)
        await pilot.press("a")
        assert set(app.selection) == set(fonts)
        await pilot.press("n")
        assert app.selection == {}


async def test_review_and_dry_run_to_completion(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await search(pilot, "jq")
        await pilot.press("space")
        await search(pilot, "spotify")
        await pilot.press("space")
        await pilot.press("escape", "r")
        await pilot.pause(0.5)
        review = app.screen
        assert isinstance(review, ReviewScreen) and review.plan is not None
        assert {ip.item.id for ip in review.plan.items} == {"jq", "spotify", "flatpak"}
        await pilot.press("enter")
        await pilot.pause(0.5)
        run = app.screen
        assert isinstance(run, RunScreen)
        await pilot.pause(0.5)
        assert run.finished and run.summary is not None
        assert set(run.summary.statuses.values()) == {ItemStatus.PREVIEWED}
        assert app.selection  # a dry run keeps the selection
        await pilot.click("#done")
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)


async def test_review_requires_ack_for_scripts_in_live_mode(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app(dry_run=False)
    async with app.run_test(size=SIZE) as pilot:
        await search(pilot, "starship")
        await pilot.press("space", "escape", "r")
        await pilot.pause(0.5)
        review = app.screen
        assert isinstance(review, ReviewScreen) and review.plan is not None
        assert review.plan.warnings
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)  # blocked until acknowledged


async def test_review_with_nothing_to_do(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app(installed={"jq"})
    async with app.run_test(size=SIZE) as pilot:
        await search(pilot, "jq")
        await pilot.press("space", "escape", "r")
        await pilot.pause(0.5)
        assert app.screen.query_one("#install", Button).disabled


async def test_review_without_selection_warns(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("r")
        assert isinstance(app.screen, MainScreen)


async def test_profiles_load_and_save(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, ProfilesScreen)
        await pilot.click("#load")  # first profile: Essentials
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        assert "git" in app.selection and "jq" in app.selection

        await pilot.press("p")
        await pilot.pause()
        app.screen.query_one("#profile-name", Input).value = "My Box"
        await pilot.click("#save")
        await pilot.pause()
        saved = app.services.paths.profiles_dir / "my-box.yaml"
        assert saved.exists()
        assert "jq" in saved.read_text()


async def test_settings_save_and_validation(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("s")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        screen.query_one("#git-email", Input).value = "not-an-email"
        await pilot.click("#save")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)  # stays open with an error

        screen.query_one("#git-name", Input).value = "Ada Lovelace"
        screen.query_one("#git-email", Input).value = "ada@example.com"
        screen.query_one("#theme", Select).value = "nord"
        await pilot.pause(0.6)  # outside the double-click window of the first click
        await pilot.click("#save")
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        stored = load_settings(app.services.paths.settings_file)
        assert (stored.git_name, stored.git_email, stored.theme) == (
            "Ada Lovelace",
            "ada@example.com",
            "nord",
        )


async def test_settings_cancel_restores_theme(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        original = app.theme
        await pilot.press("s")
        await pilot.pause()
        app.screen.query_one("#theme", Select).value = "dracula"
        await pilot.pause()
        assert app.theme == "dracula"
        await pilot.press("escape")
        await pilot.pause()
        assert app.theme == original


async def test_theme_cycle_persists(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        assert app.theme == "catppuccin-mocha"
        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "catppuccin-macchiato"
        assert load_settings(app.services.paths.settings_file).theme == "catppuccin-macchiato"


@pytest.mark.parametrize("theme", THEME_NAMES)
async def test_every_theme_renders(make_app, theme: str) -> None:  # type: ignore[no-untyped-def]
    app = make_app(theme=theme)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app.theme == theme
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")


async def test_invalid_saved_theme_falls_back(make_app) -> None:  # type: ignore[no-untyped-def]
    app = make_app(theme="does-not-exist")
    async with app.run_test(size=SIZE):
        assert app.theme == "catppuccin-mocha"


class _Failing(Operation):
    title = "explode"

    def preview(self) -> list[str]:
        return ["explode"]

    async def run(self, ctx: RunContext) -> Result:
        return Result.failed("kaboom", returncode=1, tail="last lines of output")


async def test_failure_dialog_skip_marks_item_failed(make_app, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    app = make_app(dry_run=False)
    item = catalog.items["jq"]
    plan = Plan(steps=[Step("Install jq", "install", ("jq",), [_Failing()])], items=[ItemPlan(item, None, 0)])
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(RunScreen(plan, dry_run=False))
        await pilot.pause(0.5)
        assert isinstance(app.screen, FailureDialog)
        await pilot.press("s")
        await pilot.pause(0.5)
        run = app.screen
        assert isinstance(run, RunScreen) and run.finished
        assert run.summary is not None and run.summary.statuses == {"jq": ItemStatus.FAILED}
        assert run.query_one("#run-items", DataTable).row_count == 1


async def test_quit_disabled_while_running(make_app, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    app = make_app(dry_run=False)
    plan = Plan(
        steps=[Step("x", "install", ("jq",), [_Failing()])], items=[ItemPlan(catalog.items["jq"], None, 0)]
    )
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(RunScreen(plan, dry_run=False))
        await pilot.pause(0.5)
        await pilot.press("a")  # abort via the failure dialog
        await pilot.pause(0.5)
        run = app.screen
        assert isinstance(run, RunScreen) and run.summary is not None and run.summary.aborted
