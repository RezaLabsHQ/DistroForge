"""Run screen: live progress, per-item status and streaming output."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, ProgressBar, RichLog, Static

from distroforge.core import privilege
from distroforge.core.executor import Executor, Result
from distroforge.engine.ops import RunContext
from distroforge.engine.planner import Plan, Step
from distroforge.engine.runner import (
    Decision,
    Event,
    ItemChanged,
    ItemStatus,
    OutputLine,
    PlanRunner,
    StepFinished,
    StepStarted,
    Summary,
)
from distroforge.tui.colors import colour
from distroforge.tui.screens.dialogs import ConfirmDialog, FailureDialog

if TYPE_CHECKING:
    from distroforge.tui.app import DistroForgeApp

STATUS_STYLE = {
    ItemStatus.PENDING: ("·  pending", "dim"),
    ItemStatus.RUNNING: ("⟳  working", "secondary"),
    ItemStatus.DONE: ("✓  done", "success"),
    ItemStatus.PREVIEWED: ("◌  previewed", "secondary"),
    ItemStatus.FAILED: ("✗  failed", "error"),
    ItemStatus.BLOCKED: ("⊘  blocked", "warning"),
    ItemStatus.CANCELLED: ("–  cancelled", "dim"),
}


class RunScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+l", "clear_log", "Clear log", show=False),
    ]

    def __init__(self, plan: Plan, *, dry_run: bool) -> None:
        super().__init__()
        self.plan = plan
        self.dry_run = dry_run
        self.finished = False
        self.summary: Summary | None = None

    @property
    def df(self) -> DistroForgeApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        mode = "Dry run — nothing will be changed" if self.dry_run else "Installing"
        yield Static(mode, id="run-title")
        yield ProgressBar(total=max(1, len(self.plan.steps)), show_eta=False, id="progress")
        yield Static("", id="run-step")
        with Horizontal(id="run-body"):
            with Vertical(id="run-side"):
                yield DataTable(id="run-items", cursor_type="none", zebra_stripes=True)
                yield Static(id="run-summary")
            yield RichLog(id="log", wrap=True, max_lines=5000, markup=False, highlight=False)
        with Horizontal(id="run-actions"):
            yield Static(classes="spacer")
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Done", id="done", variant="success", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#run-items").border_title = "Items"
        self.query_one("#log").border_title = "Output"
        self.query_one("#run-summary").display = False
        table = self.query_one("#run-items", DataTable)
        table.add_column("Item", key="item")
        table.add_column("Status", key="status", width=14)
        for ip in self.plan.items:
            table.add_row(ip.item.name, self._status_text(ItemStatus.PENDING), key=ip.item.id)
        self.execute()

    def _colour(self, name: str) -> str:
        return colour(self.app, name)

    def _status_text(self, status: ItemStatus) -> Text:
        label, tone = STATUS_STYLE[status]
        return Text(label, style=tone if tone == "dim" else f"bold {self._colour(tone)}")

    # ── runner plumbing ──

    def _on_event(self, event: Event) -> None:
        log = self.query_one("#log", RichLog)
        if isinstance(event, OutputLine):
            log.write(Text(event.line))
        elif isinstance(event, StepStarted):
            header = Text(
                f"\n▶ [{event.index}/{event.total}] {event.step.title}",
                style=f"bold {self._colour('primary')}",
            )
            log.write(header)
            self.query_one("#run-step", Static).update(
                Text(f"Step {event.index}/{event.total}: {event.step.title}")
            )
        elif isinstance(event, StepFinished):
            self.query_one("#progress", ProgressBar).advance(1)
            if not event.result.status.ok:
                log.write(Text(f"✗ {event.result.message}", style=f"bold {self._colour('error')}"))
        elif isinstance(event, ItemChanged):
            table = self.query_one("#run-items", DataTable)
            with contextlib.suppress(Exception):
                table.update_cell(event.item_id, "status", self._status_text(event.status))

    async def _on_failure(self, step: Step, result: Result) -> Decision:
        decision: Decision = await self.app.push_screen_wait(FailureDialog(step, result))
        return decision

    @work(exclusive=True, group="run")
    async def execute(self) -> None:
        workdir = Path(tempfile.mkdtemp(prefix="distroforge-"))
        ctx = RunContext(system=self.df.services.system, executor=Executor(), workdir=workdir)
        runner = PlanRunner(
            self.plan, ctx, dry_run=self.dry_run, on_event=self._on_event, on_failure=self._on_failure
        )
        keepalive = None
        if not self.dry_run and self.plan.needs_root:
            keepalive = asyncio.create_task(privilege.keepalive())
        try:
            self.summary = await runner.run()
        except asyncio.CancelledError:
            self.query_one("#log", RichLog).write(Text("\nCancelled by user.", style="bold"))
            self.summary = Summary(
                dict(runner.statuses), dict(runner.messages), aborted=True, dry_run=self.dry_run
            )
        finally:
            if keepalive is not None:
                keepalive.cancel()
            shutil.rmtree(workdir, ignore_errors=True)
            if not self.dry_run:
                self.df.services.refresh_state()
        self._finish()

    def _finish(self) -> None:
        self.finished = True
        summary = self.summary
        assert summary is not None
        text = Text()
        done_status = ItemStatus.PREVIEWED if summary.dry_run else ItemStatus.DONE
        text.append(
            f"{summary.count(done_status)} {'previewed' if summary.dry_run else 'done'}",
            style=f"bold {self._colour('success')}",
        )
        for status, tone in (
            (ItemStatus.FAILED, "error"),
            (ItemStatus.BLOCKED, "warning"),
            (ItemStatus.CANCELLED, ""),
        ):
            if summary.count(status):
                style = f"bold {self._colour(tone)}" if tone else "bold"
                text.append(f"   {summary.count(status)} {status.value}", style=style)
        for item_id, message in summary.messages.items():
            text.append(f"\n{item_id}: {message}", style="dim")
        if not summary.dry_run and summary.ok:
            text.append(
                "\n\nSome changes (groups, login shell) apply after you log out and back in.", style="italic"
            )
        text.append(f"\nFull log: {self.df.services.log_file}", style="dim")
        panel = self.query_one("#run-summary", Static)
        panel.border_title = "Finished" if summary.ok else "Finished with problems"
        panel.update(text)
        panel.display = True
        self.query_one("#run-step", Static).update(
            Text("All done." if summary.ok else "Finished — see the summary.", style="bold")
        )
        self.query_one("#cancel", Button).disabled = True
        done = self.query_one("#done", Button)
        done.disabled = False
        done.focus()
        if not summary.dry_run:
            for item_id, status in summary.statuses.items():
                if status is ItemStatus.DONE:
                    self.df.selection.pop(item_id, None)

    # ── user actions ──

    @on(Button.Pressed, "#done")
    def _done(self) -> None:
        self.app.pop_screen()
        from distroforge.tui.screens.main import MainScreen

        if isinstance(self.app.screen, MainScreen) and not self.dry_run:
            self.app.screen.rescan()

    @on(Button.Pressed, "#cancel")
    def _cancel_pressed(self) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        if self.finished:
            self._done()
            return

        def confirmed(ok: bool | None) -> None:
            if ok:
                self.workers.cancel_group(self, "run")

        self.app.push_screen(
            ConfirmDialog(
                "Stop now?",
                "The current command will be terminated. Items not yet processed are left untouched.",
                confirm="Stop",
                danger=True,
            ),
            confirmed,
        )

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()
