"""Command-line entry point.

``distroforge`` with no arguments opens the full-screen TUI. Subcommands give
the same engine to scripts and CI::

    distroforge list [--category C] [--installed]
    distroforge apply git docker --dry-run
    distroforge apply --profile developer --yes
    distroforge profiles
    distroforge doctor
    distroforge validate my-apps.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from distroforge import __version__
from distroforge.catalog.loader import load_catalog
from distroforge.core import privilege
from distroforge.core.executor import Executor, Result
from distroforge.core.system import Family
from distroforge.engine.ops import RunContext
from distroforge.engine.planner import Plan, PlanError, Step
from distroforge.engine.profiles import Profile, load_profile_file, load_profiles
from distroforge.engine.runner import (
    Decision,
    Event,
    ItemChanged,
    ItemStatus,
    OutputLine,
    PlanRunner,
    StepStarted,
)
from distroforge.services import Services, bootstrap

console = Console(highlight=False)
err = Console(stderr=True, highlight=False)

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_PLAN, EXIT_INTERRUPTED = 0, 1, 2, 3, 130


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="distroforge",
        description="DistroForge — forge your Linux setup. Run without arguments for the full-screen app.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--distro",
        choices=[f.value for f in Family if f is not Family.UNKNOWN],
        help="override package-manager family detection",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    tui = sub.add_parser("tui", help="open the full-screen app (default)")
    tui.add_argument("--dry-run", action="store_true", help="start with dry-run enabled")

    lst = sub.add_parser("list", help="list catalog items")
    lst.add_argument("--category", help="only this category id")
    lst.add_argument("--installed", action="store_true", help="also check what is installed (slower)")

    apply = sub.add_parser("apply", help="install items / a profile without the UI")
    apply.add_argument("items", nargs="*", help="catalog item ids")
    apply.add_argument("--profile", "-p", help="built-in/user profile id, or a path to a profile file")
    apply.add_argument(
        "--method",
        "-m",
        action="append",
        default=[],
        metavar="ITEM=METHOD",
        help="force a method, e.g. --method vlc=flatpak (repeatable)",
    )
    apply.add_argument("--dry-run", "-n", action="store_true", help="show every command, change nothing")
    apply.add_argument("--yes", "-y", action="store_true", help="don't ask for confirmation")
    apply.add_argument("--reinstall", action="store_true", help="run steps even if already installed")
    apply.add_argument("--fail-fast", action="store_true", help="stop at the first failure")
    apply.add_argument("--verbose", "-v", action="store_true", help="stream command output")

    sub.add_parser("profiles", help="list available profiles")
    sub.add_parser("doctor", help="show detection results and check the environment")

    validate = sub.add_parser("validate", help="validate catalog YAML files")
    validate.add_argument("files", nargs="+", type=Path)
    return parser


# ── commands ────────────────────────────────────────


def cmd_tui(services: Services, dry_run: bool) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        err.print("[red]The interactive app needs a terminal.[/] Use [bold]distroforge apply[/] for scripts.")
        return EXIT_USAGE
    from distroforge.tui.app import DistroForgeApp

    DistroForgeApp(services, dry_run=dry_run).run()
    return EXIT_OK


def cmd_list(services: Services, category: str | None, with_state: bool) -> int:
    catalog = services.catalog
    if category and category not in catalog.categories:
        err.print(f"[red]Unknown category[/] {category!r}. Known: {', '.join(catalog.sorted_category_ids())}")
        return EXIT_USAGE
    resolver = services.resolver()
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in ("id", "name", "category", "method", *(["installed"] if with_state else [])):
        table.add_column(column)
    for cid, items in catalog.by_category().items():
        if category and cid != category:
            continue
        for item in items:
            method = resolver.choose(item)
            supported = resolver.supported(item)
            label = method.label if method else ("action" if supported else "[dim]n/a[/]")
            row = [item.id, item.name, cid, label]
            if with_state:
                row.append("✓" if supported and resolver.is_installed(item) else "")
            table.add_row(*row)
    console.print(table)
    return EXIT_OK


def cmd_profiles(services: Services) -> int:
    for profile in load_profiles(services.paths.profiles_dir):
        origin = "built-in" if profile.builtin else str(profile.path)
        console.print(
            f"[bold]{profile.id:<14}[/] {profile.name}  [dim]({len(profile.items)} items, {origin})[/]"
        )
        if profile.description:
            console.print(f"  [dim]{profile.description}[/]")
    return EXIT_OK


def cmd_doctor(services: Services) -> int:
    s = services.system
    rows = [
        ("Version", __version__),
        ("Distro", f"{s.distro_name}  (ID={s.os.id}, ID_LIKE={' '.join(s.os.id_like) or '—'})"),
        ("Family", f"{s.family.label} → {s.package_manager}"),
        ("Arch / kernel", f"{s.arch} / {s.kernel}"),
        ("CPU / RAM", f"{s.cpu} / {s.ram_gb} GB"),
        ("GPU", f"{s.gpu_vendor.value}: {s.gpu_name or '—'}"),
        ("Desktop", f"{s.desktop or '—'} ({s.session_type or '—'})"),
        ("User", f"{s.username}{'  [red](root!)[/]' if s.is_root else ''}"),
        ("sudo", "available" if privilege.sudo_available() else "[red]missing[/]"),
        ("Flatpak", "installed" if shutil.which("flatpak") else "not installed (will be added when needed)"),
        ("AUR helper", s.aur_helper or "—"),
        ("Catalog", f"{len(services.catalog.items)} items, {len(services.catalog.errors)} problem(s)"),
        ("Config", str(services.paths.config)),
        ("User catalog", str(services.paths.user_catalog_dir)),
        ("Log", str(services.log_file)),
    ]
    for key, value in rows:
        console.print(f"[bold]{key:<14}[/] {value}")
    for problem in services.catalog.errors:
        console.print(f"  [yellow]⚠[/] {problem}")
    if s.family is Family.UNKNOWN:
        console.print(
            "\n[yellow]Unknown distro family.[/] Only Flatpak items will be offered; "
            "use --distro to override."
        )
    return EXIT_OK if not services.catalog.errors else EXIT_FAILED


def cmd_validate(files: list[Path]) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        for path in files:
            if not path.is_file():
                err.print(f"[red]Not a file:[/] {path}")
                return EXIT_USAGE
            shutil.copy(path, Path(tmp) / path.name)
        catalog = load_catalog(Path(tmp))
    # Built-in data is validated by the test suite, so every problem here is in the given files.
    if catalog.errors:
        for problem in catalog.errors:
            console.print(f"[red]✗[/] {problem}")
        return EXIT_FAILED
    user_items = [i for i in catalog.items.values() if i.source.startswith("user")]
    console.print(f"[green]✓[/] {len(files)} file(s) valid — {len(user_items)} item(s)")
    return EXIT_OK


def _selection(services: Services, args: argparse.Namespace) -> dict[str, str | None] | None:
    selection: dict[str, str | None] = {}
    if args.profile:
        candidate = Path(args.profile)
        profile: Profile | None
        if candidate.suffix in (".yaml", ".yml") and candidate.exists():
            profile = load_profile_file(candidate)
        else:
            profile = next(
                (p for p in load_profiles(services.paths.profiles_dir) if p.id == args.profile), None
            )
        if profile is None:
            err.print(f"[red]Unknown profile[/] {args.profile!r}. See: distroforge profiles")
            return None
        chosen, unknown = profile.selection(services.catalog)
        for item_id in unknown:
            err.print(f"[yellow]⚠ profile item {item_id!r} is not in the catalog — ignored[/]")
        selection.update(chosen)
    for item_id in args.items:
        if item_id not in services.catalog.items:
            err.print(f"[red]Unknown item[/] {item_id!r}. See: distroforge list")
            return None
        selection.setdefault(item_id, None)
    for spec in args.method:
        item_id, sep, method = spec.partition("=")
        if not sep or item_id not in services.catalog.items:
            err.print(f"[red]Bad --method[/] {spec!r} (expected ITEM=METHOD for a known item)")
            return None
        selection[item_id] = method
    return selection


def _print_plan(plan: Plan) -> None:
    for item, reason in plan.skipped:
        console.print(f"[green]✓[/] {item.name} [dim]— {reason}[/]")
    for item, reason in plan.unsupported:
        console.print(f"[yellow]⊘[/] {item.name} [dim]— {reason}[/]")
    for index, step in enumerate(plan.steps, 1):
        console.print(
            f"\n[bold]{index:>2}. {step.title}[/]" + ("  [yellow]sudo[/]" if step.needs_root else "")
        )
        for op in step.ops:
            for line in op.preview():
                console.print(Text(f"      {line}", style="dim" if line.lstrip().startswith("#") else ""))
    for warning in plan.warnings:
        console.print(f"[yellow]⚠ {warning}[/]")


def cmd_apply(services: Services, args: argparse.Namespace) -> int:
    selection = _selection(services, args)
    if selection is None:
        return EXIT_USAGE
    if not selection:
        err.print("Nothing selected. Pass item ids and/or --profile.")
        return EXIT_USAGE
    if services.system.is_root and not args.dry_run:
        err.print(
            "[red]Don't run DistroForge as root.[/] Run it as your user; it uses sudo only where needed."
        )
        return EXIT_USAGE

    try:
        plan = services.planner().build(selection, reinstall=args.reinstall)
    except PlanError as exc:
        err.print(f"[red]{exc}[/]")
        return EXIT_PLAN

    _print_plan(plan)
    if plan.empty:
        console.print("\n[green]Nothing to do.[/]")
        return EXIT_OK

    if not args.dry_run and not args.yes:
        if not sys.stdin.isatty():
            err.print("[red]Refusing to make changes without a terminal.[/] Add --yes to confirm.")
            return EXIT_USAGE
        answer = console.input("\n[bold]Proceed? [y/N] [/]").strip().lower()
        if answer not in ("y", "yes"):
            console.print("Cancelled — nothing changed.")
            return EXIT_OK
    if not args.dry_run and plan.needs_root and not privilege.authenticate_interactive():
        err.print("[red]sudo authentication failed.[/]")
        return EXIT_FAILED

    names = {ip.item.id: ip.item.name for ip in plan.items}

    def on_event(event: Event) -> None:
        if isinstance(event, StepStarted):
            console.print(f"[bold cyan]▶[/] [{event.index}/{event.total}] {event.step.title}")
        elif isinstance(event, OutputLine) and (args.verbose or args.dry_run):
            console.print(Text(f"    {event.line}", style="dim"))
        elif isinstance(event, ItemChanged) and event.status in (ItemStatus.FAILED, ItemStatus.BLOCKED):
            colour = "red" if event.status is ItemStatus.FAILED else "yellow"
            console.print(
                f"  [{colour}]{event.status.value}:[/] {names.get(event.item_id)} — {event.message}"
            )

    async def on_failure(step: Step, result: Result) -> Decision:
        if result.output_tail and not args.verbose:
            console.print(Text(result.output_tail, style="dim"))
        return Decision.ABORT if args.fail_fast else Decision.SKIP

    async def run() -> int:
        workdir = Path(tempfile.mkdtemp(prefix="distroforge-"))
        keepalive = (
            asyncio.create_task(privilege.keepalive()) if plan.needs_root and not args.dry_run else None
        )
        try:
            runner = PlanRunner(
                plan,
                RunContext(system=services.system, executor=Executor(), workdir=workdir),
                dry_run=args.dry_run,
                on_event=on_event,
                on_failure=on_failure,
            )
            summary = await runner.run()
        finally:
            if keepalive:
                keepalive.cancel()
            shutil.rmtree(workdir, ignore_errors=True)
        done = summary.count(ItemStatus.PREVIEWED if args.dry_run else ItemStatus.DONE)
        console.print(
            f"\n[bold]{'Previewed' if args.dry_run else 'Done'}:[/] {done}   "
            f"[red]failed: {summary.count(ItemStatus.FAILED)}[/]   "
            f"[yellow]blocked: {summary.count(ItemStatus.BLOCKED)}[/]   "
            f"[dim]log: {services.log_file}[/]"
        )
        return EXIT_OK if summary.ok else EXIT_FAILED

    return asyncio.run(run())


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        return cmd_validate(args.files)

    family = Family(args.distro) if args.distro else None
    try:
        services = bootstrap(family=family)
        command = args.command or "tui"
        if command == "tui":
            return cmd_tui(services, getattr(args, "dry_run", False))
        if command == "list":
            return cmd_list(services, args.category, args.installed)
        if command == "profiles":
            return cmd_profiles(services)
        if command == "doctor":
            return cmd_doctor(services)
        if command == "apply":
            return cmd_apply(services, args)
    except KeyboardInterrupt:
        err.print("\nInterrupted.")
        return EXIT_INTERRUPTED
    return EXIT_USAGE


def entrypoint() -> None:
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
