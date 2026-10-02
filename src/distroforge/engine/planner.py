"""Turn a user selection into an ordered, batched, dependency-safe plan.

Ordering rules:

1. ``prepare`` — early actions (full upgrade) and package-database refreshes.
2. For each dependency *level* (an item's level is 1 + its deepest dependency):
   ``pre`` (repos) → native batch per backend → Flatpak batch → AUR batch →
   upstream scripts → ``post`` (services, groups, shell init).

So every dependency is fully set up before anything that needs it, while
independent packages are still installed in a single transaction per backend.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from distroforge.actions import get_action
from distroforge.backends import Backend
from distroforge.catalog.models import ActionRef, Catalog, Item, Method
from distroforge.engine.ops import Operation
from distroforge.engine.resolve import Environment, Resolver, script_op

#: item id → backend override (``None`` = automatic)
Selection = Mapping[str, str | None]

FLATPAK_ITEM = "flatpak"


class PlanError(ValueError):
    pass


@dataclass
class Step:
    title: str
    stage: str  # prepare | pre | install | script | post
    item_ids: tuple[str, ...]
    ops: list[Operation]
    #: For batched installs: rebuild ops for a subset of items (failure isolation).
    rebuild: Callable[[tuple[str, ...]], list[Operation]] | None = None

    @property
    def needs_root(self) -> bool:
        return any(op.needs_root for op in self.ops)


@dataclass(frozen=True)
class ItemPlan:
    item: Item
    method: Method | None
    level: int


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    items: list[ItemPlan] = field(default_factory=list)
    skipped: list[tuple[Item, str]] = field(default_factory=list)
    unsupported: list[tuple[Item, str]] = field(default_factory=list)
    #: dependency graph restricted to planned items: id → ids it requires
    requires: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def needs_root(self) -> bool:
        return any(step.needs_root for step in self.steps)

    @property
    def warnings(self) -> list[str]:
        seen: dict[str, None] = {}
        for step in self.steps:
            for op in step.ops:
                if op.warning:
                    seen[op.warning] = None
        return list(seen)

    @property
    def empty(self) -> bool:
        return not self.steps

    def dependents_of(self, item_id: str) -> set[str]:
        """Every planned item that (transitively) requires ``item_id``."""
        found: set[str] = set()
        frontier = {item_id}
        while frontier:
            frontier = {
                other for other, reqs in self.requires.items() if frontier & set(reqs) and other not in found
            }
            found |= frontier
        return found


class Planner:
    def __init__(self, catalog: Catalog, env: Environment) -> None:
        self.catalog = catalog
        self.env = env
        self.resolver = Resolver(env)

    def _deps(self, item: Item, method: Method | None) -> list[str]:
        deps = list(item.requires)
        needs_flatpak = method is not None and method.backend == "flatpak"
        if needs_flatpak and item.id != FLATPAK_ITEM and FLATPAK_ITEM in self.catalog.items:
            deps.append(FLATPAK_ITEM)
        return deps

    def build(self, selection: Selection, *, reinstall: bool = False) -> Plan:
        plan = Plan()
        order: list[str] = []
        methods: dict[str, Method | None] = {}
        visiting: list[str] = []

        def visit(item_id: str) -> None:
            if item_id in methods:
                return
            if item_id in visiting:
                cycle = " → ".join([*visiting[visiting.index(item_id) :], item_id])
                raise PlanError(f"Dependency cycle: {cycle}")
            item = self.catalog.items.get(item_id)
            if item is None:
                raise PlanError(f"Unknown item '{item_id}'")
            visiting.append(item_id)
            method = self.resolver.choose(item, selection.get(item_id))
            for dep in self._deps(item, method):
                visit(dep)
            visiting.pop()
            methods[item_id] = method
            order.append(item_id)

        for item_id in selection:
            visit(item_id)

        blocked: set[str] = set()
        levels: dict[str, int] = {}
        for item_id in order:
            item = self.catalog.items[item_id]
            method = methods[item_id]
            deps = self._deps(item, method)
            failed_deps = [d for d in deps if d in blocked]
            if failed_deps:
                plan.unsupported.append(
                    (item, f"Requires {', '.join(failed_deps)}, which can't be installed here")
                )
                blocked.add(item_id)
                continue
            if not self.resolver.supported(item):
                plan.unsupported.append((item, self.resolver.unsupported_reason(item)))
                blocked.add(item_id)
                continue
            if (
                not reinstall
                and self.env.settings.skip_installed
                and self.resolver.is_installed(item, method)
            ):
                plan.skipped.append((item, "already installed"))
                continue
            level = 1 + max((levels[d] for d in deps if d in levels), default=-1)
            levels[item_id] = level
            plan.items.append(ItemPlan(item, method, level))
            plan.requires[item_id] = tuple(d for d in deps if d in levels)

        self._emit_steps(plan, reinstall=reinstall)
        return plan

    # ── step generation ──

    def _action_steps(
        self, item: Item, refs: tuple[ActionRef, ...], stage: str, *, reinstall: bool
    ) -> list[Step]:
        steps = []
        for ref in refs:
            if not reinstall and self.resolver.action_applied(ref):
                continue
            ops = self.resolver.action_ops(ref)
            if ops:
                steps.append(Step(ref.describe(self.env.system), stage, (item.id,), ops))
        return steps

    def _emit_steps(self, plan: Plan, *, reinstall: bool) -> None:
        backends = self.env.backends
        prepare: list[Step] = []
        early_refs = {ip.item.id: [ref for ref in ip.item.post if _is_early(ref.name)] for ip in plan.items}
        for item_id, refs in early_refs.items():
            item = self.catalog.items[item_id]
            prepare += self._action_steps(item, tuple(refs), "prepare", reinstall=True)

        upgrading = bool(prepare)  # a full upgrade already refreshes package metadata
        refreshed: set[str] = set()
        body: list[Step] = []
        for level in sorted({ip.level for ip in plan.items}):
            tier = [ip for ip in plan.items if ip.level == level]
            pre: list[Step] = []
            batches: dict[str, dict[str, tuple[str, ...]]] = {}
            scripts: list[Step] = []
            post: list[Step] = []

            for ip in tier:
                item, method = ip.item, ip.method
                if method is not None:
                    pre += self._action_steps(item, method.pre, "pre", reinstall=reinstall)
                    if method.backend == "script":
                        if reinstall or not self.resolver.check_hit(item):
                            op = script_op(item, method, self.env.system)
                            scripts.append(Step(f"Install {item.name}", "script", (item.id,), [op]))
                    elif reinstall or not self.resolver.packages_installed(method):
                        batches.setdefault(method.backend, {})[item.id] = method.packages
                    post += self._action_steps(item, method.post, "post", reinstall=reinstall)
                late = tuple(ref for ref in item.post if not _is_early(ref.name))
                post += self._action_steps(item, late, "post", reinstall=reinstall)

            installs: list[Step] = []
            for backend_name in sorted(batches, key=_batch_order):
                backend = backends.get(backend_name)
                packages_by_item = batches[backend_name]
                if backend_name not in refreshed:
                    refreshed.add(backend_name)
                    refresh = backend.refresh_ops()
                    if refresh and not upgrading:
                        prepare.append(Step(refresh[0].title, "prepare", (), refresh))

                def rebuild(
                    subset: tuple[str, ...],
                    b: Backend = backend,
                    p: dict[str, tuple[str, ...]] = packages_by_item,
                ) -> list[Operation]:
                    return b.install_ops(_dedupe(pkg for i in subset for pkg in p[i]))

                ids = tuple(packages_by_item)
                names = ", ".join(self.catalog.items[i].name for i in ids)
                installs.append(
                    Step(f"{backend.label}: install {names}", "install", ids, rebuild(ids), rebuild=rebuild)
                )

            body += pre + installs + scripts + post

        plan.steps = prepare + body


def _is_early(action_name: str) -> bool:
    return get_action(action_name).early


def _batch_order(backend: str) -> int:
    return {"apt": 0, "dnf": 0, "pacman": 0, "flatpak": 1, "aur": 2}.get(backend, 3)


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
