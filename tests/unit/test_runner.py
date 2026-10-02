from pathlib import Path

from distroforge.core.executor import Result, Status
from distroforge.core.system import Family
from distroforge.engine.ops import Operation, RunContext
from distroforge.engine.planner import ItemPlan, Plan, Step
from distroforge.engine.runner import Decision, ItemChanged, ItemStatus, OutputLine, PlanRunner

from ..conftest import make_system


class FakeOp(Operation):
    def __init__(self, name: str, outcomes: list[bool], log: list[str]) -> None:
        self.title = name
        self._outcomes = outcomes
        self._log = log

    def preview(self) -> list[str]:
        return [f"run {self.title}"]

    async def run(self, ctx: RunContext) -> Result:
        self._log.append(self.title)
        ok = self._outcomes.pop(0) if self._outcomes else True
        return Result.success() if ok else Result.failed(f"{self.title} broke")


def _item(item_id: str):  # type: ignore[no-untyped-def]
    from distroforge.catalog.models import Item

    return Item(id=item_id, name=item_id, category="system", post=())


def make_plan(steps: list[Step], items: list[str], requires: dict[str, tuple[str, ...]] | None = None) -> Plan:
    return Plan(steps=steps, items=[ItemPlan(_item(i), None, 0) for i in items], requires=requires or {})


def ctx(tmp_path: Path) -> RunContext:
    return RunContext(system=make_system(Family.FEDORA, tmp_path), workdir=tmp_path)


async def test_dry_run_executes_nothing_and_reports_previewed(tmp_path: Path) -> None:
    log: list[str] = []
    events = []
    plan = make_plan([Step("s", "install", ("a",), [FakeOp("a", [], log)])], ["a"])
    summary = await PlanRunner(plan, ctx(tmp_path), dry_run=True, on_event=events.append).run()
    assert log == []
    assert summary.statuses == {"a": ItemStatus.PREVIEWED}
    assert summary.ok and summary.dry_run
    assert OutputLine("run a") in events


async def test_batch_failure_isolated_per_item(tmp_path: Path) -> None:
    log: list[str] = []

    def rebuild(ids: tuple[str, ...]) -> list[Operation]:
        if len(ids) > 1:
            return [FakeOp("batch", [False], log)]
        return [FakeOp(ids[0], [ids[0] != "bad"], log)]

    step = Step("install", "install", ("good", "bad"), rebuild(("good", "bad")), rebuild=rebuild)
    summary = await PlanRunner(make_plan([step], ["good", "bad"]), ctx(tmp_path)).run()
    assert log == ["batch", "good", "bad"]
    assert summary.statuses == {"good": ItemStatus.DONE, "bad": ItemStatus.FAILED}
    assert summary.messages["bad"] == "bad broke"
    assert not summary.ok


async def test_dependents_of_failed_item_are_blocked_not_run(tmp_path: Path) -> None:
    log: list[str] = []
    plan = make_plan(
        [
            Step("a", "install", ("a",), [FakeOp("a", [False], log)]),
            Step("b", "post", ("b",), [FakeOp("b", [], log)]),
            Step("c", "post", ("c",), [FakeOp("c", [], log)]),
        ],
        ["a", "b", "c"],
        requires={"b": ("a",), "c": ()},
    )
    summary = await PlanRunner(plan, ctx(tmp_path)).run()
    assert log == ["a", "c"]
    assert summary.statuses == {"a": ItemStatus.FAILED, "b": ItemStatus.BLOCKED, "c": ItemStatus.DONE}


async def test_retry_then_success(tmp_path: Path) -> None:
    log: list[str] = []
    decisions = [Decision.RETRY]

    async def on_failure(step: Step, result: Result) -> Decision:
        return decisions.pop(0)

    plan = make_plan([Step("a", "install", ("a",), [FakeOp("a", [False, True], log)])], ["a"])
    summary = await PlanRunner(plan, ctx(tmp_path), on_failure=on_failure).run()
    assert log == ["a", "a"]
    assert summary.statuses == {"a": ItemStatus.DONE}


async def test_abort_cancels_remaining(tmp_path: Path) -> None:
    log: list[str] = []

    async def abort(step: Step, result: Result) -> Decision:
        return Decision.ABORT

    plan = make_plan(
        [Step("a", "install", ("a",), [FakeOp("a", [False], log)]), Step("b", "install", ("b",), [FakeOp("b", [], log)])],
        ["a", "b"],
    )
    summary = await PlanRunner(plan, ctx(tmp_path), on_failure=abort).run()
    assert log == ["a"]
    assert summary.aborted
    assert summary.statuses == {"a": ItemStatus.FAILED, "b": ItemStatus.CANCELLED}


async def test_item_marked_done_after_its_last_step(tmp_path: Path) -> None:
    log: list[str] = []
    changes: list[tuple[str, ItemStatus]] = []

    def on_event(event: object) -> None:
        if isinstance(event, ItemChanged):
            changes.append((event.item_id, event.status))

    plan = make_plan(
        [Step("a1", "install", ("a",), [FakeOp("a1", [], log)]), Step("b", "install", ("b",), [FakeOp("b", [], log)]),
         Step("a2", "post", ("a",), [FakeOp("a2", [], log)])],
        ["a", "b"],
    )
    await PlanRunner(plan, ctx(tmp_path), on_event=on_event).run()
    assert changes.index(("b", ItemStatus.DONE)) < changes.index(("a", ItemStatus.DONE))


async def test_skipped_status_counts_as_ok(tmp_path: Path) -> None:
    assert Status.SKIPPED.ok and not Status.FAILED.ok
