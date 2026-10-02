"""Execute a :class:`Plan`, emitting events for the UI.

* Dry-run is decided here, in one place: no operation runs, every step reports
  ``SKIPPED`` and its exact preview is emitted.
* A failed batched install is retried item-by-item so one bad package does not
  fail its neighbours.
* When an item fails, every item that depends on it is marked ``blocked``.
* On failure the ``on_failure`` callback decides: retry, skip or abort.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum

from distroforge.core.executor import Result, Status
from distroforge.core.logging import get_logger
from distroforge.engine.ops import Operation, RunContext
from distroforge.engine.planner import Plan, Step

log = get_logger("runner")


class Decision(str, Enum):
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"


class ItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    PREVIEWED = "previewed"  # dry-run
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


# ── events ──


@dataclass(frozen=True)
class StepStarted:
    step: Step
    index: int
    total: int


@dataclass(frozen=True)
class OutputLine:
    line: str


@dataclass(frozen=True)
class StepFinished:
    step: Step
    index: int
    total: int
    result: Result


@dataclass(frozen=True)
class ItemChanged:
    item_id: str
    status: ItemStatus
    message: str = ""


Event = StepStarted | OutputLine | StepFinished | ItemChanged
EventHandler = Callable[[Event], None]
FailureHandler = Callable[[Step, Result], Awaitable[Decision]]


async def _continue(_: Step, __: Result) -> Decision:
    return Decision.SKIP


@dataclass
class Summary:
    statuses: dict[str, ItemStatus]
    messages: dict[str, str] = field(default_factory=dict)
    aborted: bool = False
    dry_run: bool = False
    duration: float = 0.0

    def count(self, status: ItemStatus) -> int:
        return sum(1 for s in self.statuses.values() if s is status)

    @property
    def ok(self) -> bool:
        bad = {ItemStatus.FAILED, ItemStatus.BLOCKED, ItemStatus.CANCELLED}
        return not self.aborted and not any(s in bad for s in self.statuses.values())


class PlanRunner:
    def __init__(
        self,
        plan: Plan,
        ctx: RunContext,
        *,
        dry_run: bool = False,
        on_event: EventHandler | None = None,
        on_failure: FailureHandler | None = None,
    ) -> None:
        self.plan = plan
        self.ctx = ctx
        self.dry_run = dry_run
        self._emit_event = on_event or (lambda _e: None)
        self._on_failure = on_failure or _continue
        self.statuses: dict[str, ItemStatus] = {ip.item.id: ItemStatus.PENDING for ip in plan.items}
        self.messages: dict[str, str] = {}
        self._last_step: dict[str, int] = {}
        for index, step in enumerate(plan.steps, 1):
            for item_id in step.item_ids:
                self._last_step[item_id] = index
        ctx.on_output = lambda line: self._emit_event(OutputLine(line))

    def _set(self, item_id: str, status: ItemStatus, message: str = "") -> None:
        if item_id not in self.statuses or self.statuses[item_id] is status:
            return
        self.statuses[item_id] = status
        if message:
            self.messages[item_id] = message
        self._emit_event(ItemChanged(item_id, status, message))

    def _fail(self, item_id: str, message: str) -> None:
        self._set(item_id, ItemStatus.FAILED, message)
        for dependent in sorted(self.plan.dependents_of(item_id)):
            if self.statuses.get(dependent) in (ItemStatus.PENDING, ItemStatus.RUNNING):
                self._set(dependent, ItemStatus.BLOCKED, f"needs {item_id}, which failed")

    def _live(self, item_ids: tuple[str, ...]) -> tuple[str, ...]:
        dead = {ItemStatus.FAILED, ItemStatus.BLOCKED, ItemStatus.CANCELLED}
        return tuple(i for i in item_ids if self.statuses.get(i) not in dead)

    async def _run_ops(self, ops: list[Operation]) -> Result:
        last = Result.success()
        for op in ops:
            if self.dry_run:
                for line in op.preview():
                    self._emit_event(OutputLine(line))
                last = Result.skipped("dry run")
                continue
            last = await op.run(self.ctx)
            if not last.status.ok:
                return last
        return last

    async def _run_step(self, step: Step, index: int, total: int) -> bool:
        """Run one step. Returns False if the user aborted."""
        live = self._live(step.item_ids)
        if step.item_ids and not live:
            return True
        ops = step.rebuild(live) if step.rebuild and live != step.item_ids else step.ops

        for item_id in live:
            self._set(item_id, ItemStatus.RUNNING)
        self._emit_event(StepStarted(step, index, total))

        while True:
            result = await self._run_ops(ops)
            if result.status.ok:
                break
            # Batched install failed: isolate the culprit(s) item by item.
            if step.rebuild and len(live) > 1:
                self._emit_event(
                    OutputLine("Batch failed — retrying each item separately to isolate the failure")
                )
                failed_here = []
                for item_id in live:
                    single = await self._run_ops(step.rebuild((item_id,)))
                    if not single.status.ok:
                        failed_here.append((item_id, single))
                if not failed_here:
                    result = Result.success()
                    break
                live = tuple(i for i, _ in failed_here)
                ops = step.rebuild(live)
                result = failed_here[-1][1]
            decision = await self._on_failure(step, result)
            log.info("Step '%s' failed (%s); decision=%s", step.title, result.message, decision.value)
            if decision is Decision.RETRY:
                continue
            for item_id in live:
                self._fail(item_id, result.message or "failed")
            self._emit_event(StepFinished(step, index, total, result))
            return decision is not Decision.ABORT

        self._emit_event(StepFinished(step, index, total, result))
        done = ItemStatus.PREVIEWED if self.dry_run else ItemStatus.DONE
        for item_id in self._live(step.item_ids):
            if self._last_step.get(item_id) == index:
                self._set(item_id, done)
        return True

    async def run(self) -> Summary:
        start = time.monotonic()
        total = len(self.plan.steps)
        aborted = False
        log.info("Running plan: %d steps, %d items, dry_run=%s", total, len(self.statuses), self.dry_run)

        for index, step in enumerate(self.plan.steps, 1):
            if not await self._run_step(step, index, total):
                aborted = True
                break

        done = ItemStatus.PREVIEWED if self.dry_run else ItemStatus.DONE
        for item_id, status in self.statuses.items():
            if status in (ItemStatus.PENDING, ItemStatus.RUNNING):
                self._set(item_id, ItemStatus.CANCELLED if aborted else done)

        summary = Summary(
            dict(self.statuses), dict(self.messages), aborted, self.dry_run, time.monotonic() - start
        )
        log.info("Plan finished: %s", {s.value: summary.count(s) for s in ItemStatus if summary.count(s)})
        return summary


__all__ = [
    "Decision",
    "Event",
    "ItemChanged",
    "ItemStatus",
    "OutputLine",
    "PlanRunner",
    "Status",
    "StepFinished",
    "StepStarted",
    "Summary",
]
