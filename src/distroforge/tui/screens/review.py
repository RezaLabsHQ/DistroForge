"""Review screen: the exact plan — every command — before anything runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Label, Static, Switch, Tree

from distroforge.core import privilege
from distroforge.engine.planner import Plan, PlanError
from distroforge.tui.colors import colour

if TYPE_CHECKING:
    from distroforge.tui.app import DistroForgeApp

STAGE_LABELS = {
    "prepare": "prepare",
    "pre": "repository",
    "install": "install",
    "script": "upstream script",
    "post": "configure",
}


class ReviewScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "Back"),
        Binding("d", "toggle_dry_run", "Dry-run on/off"),
        Binding("enter", "install", "Install", show=False),
        Binding("e", "expand", "Expand all"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.plan: Plan | None = None

    @property
    def df(self) -> DistroForgeApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Static("Review plan", id="review-title")
        with Horizontal(id="review-body"):
            with Vertical(id="review-side"):
                yield Static("Planning…", id="review-summary")
                yield Static(id="review-warnings")
            yield Tree("Plan", id="plan-tree")
        with Horizontal(id="review-actions"):
            yield Label("Dry run", classes="inline-label")
            yield Switch(value=self.df.dry_run_default, id="dry-run")
            yield Checkbox("I reviewed the flagged steps", id="ack")
            yield Static(classes="spacer")
            yield Button("Back", id="back")
            yield Button("Install", id="install", variant="success", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#review-summary").border_title = "Summary"
        self.query_one("#review-warnings").border_title = "Needs your attention"
        self.query_one("#plan-tree").border_title = "Every step and command, in order"
        self.query_one("#ack").display = False
        self.query_one("#review-warnings").display = False
        self.build_plan()

    @work(thread=True, exclusive=True)
    def build_plan(self) -> None:
        try:
            plan = self.df.services.planner().build(dict(self.df.selection))
        except PlanError as exc:
            self.app.call_from_thread(self._show_error, str(exc))
            return
        self.app.call_from_thread(self._show_plan, plan)

    def _show_error(self, message: str) -> None:
        self.query_one("#review-summary", Static).update(Text(message, style="bold red"))

    def _show_plan(self, plan: Plan) -> None:
        self.plan = plan
        summary = Text()
        summary.append(f"{len(plan.items)}", style=f"bold {colour(self.app, 'primary')}")
        summary.append(" item(s) to set up\n")
        summary.append(f"{len(plan.steps)}", style=f"bold {colour(self.app, 'primary')}")
        summary.append(" step(s)\n")
        if plan.skipped:
            summary.append(
                f"\n✓ {len(plan.skipped)} already installed (skipped):\n", style=colour(self.app, "success")
            )
            summary.append(", ".join(item.name for item, _ in plan.skipped) + "\n", style="dim")
        if plan.unsupported:
            summary.append(
                f"\n⊘ {len(plan.unsupported)} not available here:\n", style=colour(self.app, "warning")
            )
            for item, reason in plan.unsupported:
                summary.append(f"  {item.name}: ", style="bold")
                summary.append(f"{reason}\n", style="dim")
        summary.append("\nAdministrator rights: ", style="bold")
        summary.append("required (sudo)" if plan.needs_root else "not needed")
        summary.append(f"\nLog: {self.df.services.log_file}", style="dim")
        self.query_one("#review-summary", Static).update(summary)

        warnings = self.query_one("#review-warnings", Static)
        if plan.warnings:
            body = Text()
            for warning in plan.warnings:
                body.append("⚠ ", style=f"bold {colour(self.app, 'warning')}")
                body.append(warning + "\n")
            warnings.update(body)
            warnings.display = True
            self.query_one("#ack").display = True

        tree: Tree[None] = self.query_one("#plan-tree", Tree)
        tree.root.expand()
        for index, step in enumerate(plan.steps, 1):
            label = Text()
            label.append(f"{index:>2}. ", style="dim")
            label.append(
                f"[{STAGE_LABELS.get(step.stage, step.stage)}] ", style=colour(self.app, "secondary")
            )
            label.append(step.title, style="bold")
            if step.needs_root:
                label.append("  sudo", style=f"bold {colour(self.app, 'warning')}")
            node = tree.root.add(label, expand=index <= 3)
            for op in step.ops:
                for line in op.preview():
                    node.add_leaf(Text(line, style="dim" if line.lstrip().startswith("#") else ""))
        if plan.empty:
            tree.root.add_leaf(Text("Nothing to do — everything selected is already in place.", style="dim"))
        install = self.query_one("#install", Button)
        install.disabled = plan.empty
        self._update_install_label()
        if not plan.empty:
            install.focus()

    def _update_install_label(self) -> None:
        dry = self.query_one("#dry-run", Switch).value
        self.query_one("#install", Button).label = "Preview (dry run)" if dry else "Install"

    @on(Switch.Changed, "#dry-run")
    def _dry_run_changed(self) -> None:
        self._update_install_label()

    def action_toggle_dry_run(self) -> None:
        switch = self.query_one("#dry-run", Switch)
        switch.value = not switch.value

    def action_expand(self) -> None:
        self.query_one("#plan-tree", Tree).root.expand_all()

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.action_back()

    @on(Button.Pressed, "#install")
    def _install_pressed(self) -> None:
        self.action_install()

    def action_install(self) -> None:
        plan = self.plan
        if plan is None or plan.empty:
            return
        dry_run = self.query_one("#dry-run", Switch).value
        if not dry_run and plan.warnings and not self.query_one("#ack", Checkbox).value:
            self.notify("Tick “I reviewed the flagged steps” to continue.", severity="warning")
            return
        if not dry_run and plan.needs_root and not privilege.credentials_cached():
            if not privilege.sudo_available():
                self.notify("sudo is not installed — cannot perform administrator steps.", severity="error")
                return
            with self.app.suspend():
                authenticated = privilege.authenticate_interactive()
            if not authenticated:
                self.notify("Authentication failed or was cancelled.", severity="error")
                return
        from distroforge.tui.screens.run import RunScreen

        self.app.switch_screen(RunScreen(plan, dry_run=dry_run))
