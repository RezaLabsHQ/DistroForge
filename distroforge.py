#!/usr/bin/env python3
"""
DistroForge — Linux Distro Setup Automation
============================================
A professional terminal-based tool to automate the complete setup
of a fresh Linux installation.

Usage:
    python3 distroforge.py                    # Interactive mode
    python3 distroforge.py --phases system,shell,dev  # Specific phases
    python3 distroforge.py --dry-run          # Preview without executing
    python3 distroforge.py --yes              # Skip confirmations
    python3 distroforge.py --list             # List available phases

Built by Hamid at Reza Labs HQ
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

import yaml
from rich.console import Console

from core.detector import DistroFamily, detect_system
from core.logger import ForgeLogger
from core.runner import Runner
from core.ui import (
    confirm_proceed,
    select_distro,
    select_phase,
    show_banner,
    show_completion,
    show_system_info,
)
from phases.apps import AppsPhase
from phases.dev import DevPhase
from phases.gaming import GamingPhase
from phases.qol import QoLPhase
from phases.shell import ShellPhase

# Import phases
from phases.system import SystemPhase
from phases.verify import VerifyPhase

console = Console()

VERSION = "1.0.0"

# ── Phase Registry ──────────────────────────────────
# Order matters: phases run in this sequence
PHASE_REGISTRY = [
    ("system", "System Foundation — updates, essentials, GPU drivers", SystemPhase),
    ("shell", "Shell Setup — zsh, Oh My Zsh, Starship, plugins", ShellPhase),
    ("dev", "Development Environment — Node, Python, Docker, Git, editors", DevPhase),
    ("gaming", "Gaming Layer — Steam, Proton, Gamemode, MangoHud", GamingPhase),
    ("apps", "Applications & Fonts — Flatpak apps, Nerd Fonts, peripherals", AppsPhase),
    ("qol", "Quality of Life — firewall, SSD trim, system tweaks", QoLPhase),
    ("verify", "Verification — post-setup health checks and version report", VerifyPhase),
]


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override dict into base dict.
    Override values take precedence. Lists are replaced, not appended.
    """
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | None = None) -> dict:
    """
    Load configuration with local override support.

    Priority (highest to lowest):
        1. --config <path>        (explicit CLI path)
        2. config.local.yaml      (personal overrides, gitignored)
        3. config.yaml            (template defaults, committed)
    """
    project_root = Path(__file__).parent

    if config_path is not None:
        # Explicit path — use only this file
        explicit = Path(config_path)
        if not explicit.exists():
            console.print(f"[red]Config file not found: {explicit}[/]")
            sys.exit(1)
        with open(explicit) as f:
            config = yaml.safe_load(f) or {}
        console.print(f"  [dim]Config loaded from: {explicit}[/]")
        return config

    # Load base config (the committed template)
    base_path = project_root / "config.yaml"
    config = {}
    if base_path.exists():
        with open(base_path) as f:
            config = yaml.safe_load(f) or {}

    # Merge local overrides if present (gitignored personal config)
    local_path = project_root / "config.local.yaml"
    if local_path.exists():
        with open(local_path) as f:
            local_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, local_config)
        console.print("  [dim]Config loaded: config.yaml + config.local.yaml (merged)[/]")
    elif base_path.exists():
        console.print("  [dim]Config loaded: config.yaml[/]")
    else:
        console.print("[yellow]No config files found. Using defaults.[/]")

    return config


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="DistroForge — Linux Distro Setup Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
    python3 distroforge.py                         Interactive mode
    python3 distroforge.py --phases system,shell    Run specific phases
    python3 distroforge.py --dry-run                Preview commands
    python3 distroforge.py --yes                    Skip confirmations
    python3 distroforge.py --config my-config.yaml  Use custom config
    python3 distroforge.py --verbose                Show full command output
            """,
    )

    parser.add_argument(
        "--phases",
        type=str,
        help="Comma-separated list of phases to run (e.g., system,shell,dev)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview commands without executing them",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full command output including stderr",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to custom config.yaml",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available phases and exit",
    )
    parser.add_argument(
        "--distro",
        type=str,
        choices=["ubuntu", "fedora"],
        help="Override distro detection (e.g., --distro ubuntu)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # ── List phases and exit ──
    if args.list:
        console.print("\n[bold]Available phases:[/]\n")
        for key, desc, _ in PHASE_REGISTRY:
            console.print(f"  [cyan]{key:10s}[/]  {desc}")
        console.print()
        sys.exit(0)

    # ── Banner ──
    show_banner()

    # ── Load config ──
    config = load_config(args.config)

    # ── Detect system ──
    console.print("[dim]Detecting system...[/]\n")
    system_info = detect_system()
    show_system_info(system_info)

    # ── Validate distro support ──
    if args.distro:
        # Override detection
        family_override = args.distro
        console.print(f"[yellow]Distro override: {family_override}[/]\n")
    elif system_info.distro_family == DistroFamily.UNKNOWN:
        console.print("[yellow]Could not auto-detect distro family.[/]")
        family_override = select_distro()
    else:
        family_override = None
        detected = system_info.distro_family.value
        console.print(
            f"  [green]Auto-detected:[/] {system_info.distro_name} "
            f"({detected}-based)\n"
        )

    # Apply override if needed
    if family_override:
        family_map = {
            "ubuntu": DistroFamily.UBUNTU,
            "fedora": DistroFamily.FEDORA,
            "arch": DistroFamily.ARCH,
        }
        system_info.distro_family = family_map.get(family_override, DistroFamily.UNKNOWN)
        system_info.package_manager = {
            "ubuntu": "apt",
            "fedora": "dnf",
            "arch": "pacman",
        }.get(family_override, "unknown")

    # ── Phase selection ──
    if args.phases:
        selected_phases = [p.strip() for p in args.phases.split(",")]
        # Validate
        valid_keys = {key for key, _, _ in PHASE_REGISTRY}
        invalid = set(selected_phases) - valid_keys
        if invalid:
            console.print(f"[red]Unknown phases: {', '.join(invalid)}[/]")
            console.print(f"[dim]Valid phases: {', '.join(valid_keys)}[/]")
            sys.exit(1)
    else:
        # Interactive selection
        available = [(key, desc) for key, desc, _ in PHASE_REGISTRY]
        selected_phases = select_phase(available)

    # ── Confirm ──
    if not args.yes and not confirm_proceed(selected_phases, dry_run=args.dry_run):
        console.print("\n[dim]Cancelled. No changes made.[/]\n")
        sys.exit(0)

    # ── Initialize logger and runner ──
    logger = ForgeLogger(verbose=args.verbose)
    runner = Runner(logger, dry_run=args.dry_run, verbose=args.verbose)

    # ── Pre-cache sudo ──
    if not args.dry_run:
        console.print("\n[dim]Requesting sudo access...[/]\n")
        runner._cache_sudo()

    # ── Execute phases ──
    phase_map = {key: cls for key, _, cls in PHASE_REGISTRY}
    phase_results = []  # List of (key, name, icon, status, details)

    total_commands = {"passed": 0, "failed": 0, "skipped": 0}

    for i, phase_key in enumerate(selected_phases, 1):
        phase_cls = phase_map[phase_key]
        phase = phase_cls(
            runner=runner,
            logger=logger,
            config=config,
            system=system_info,
        )

        # Phase progress header
        console.print(
            f"\n  [dim]Phase {i}/{len(selected_phases)}[/]"
        )

        try:
            if phase.should_skip():
                logger.skip(f"{phase.icon} {phase.name}")
                phase_results.append((
                    phase_key, phase.name, phase.icon, "skipped", ""
                ))
                continue

            results = phase.run()

            # Aggregate command-level results
            for k in total_commands:
                total_commands[k] += results.get(k, 0)

            if results.get("failed", 0) == 0:
                phase_results.append((
                    phase_key, phase.name, phase.icon, "passed",
                    f"{results['passed']} steps"
                ))
            else:
                phase_results.append((
                    phase_key, phase.name, phase.icon, "partial",
                    f"{results['passed']} passed, {results['failed']} failed"
                ))

                # Error recovery — ask user what to do (unless --yes)
                if not args.yes and not args.dry_run:
                    console.print()
                    console.print(
                        f"  [yellow]⚠ Phase '{phase.name}' had "
                        f"{results['failed']} failed step(s).[/]"
                    )
                    choice = console.input(
                        "  [bold]Continue to next phase? "
                        "(Y)es / (S)kip remaining / (R)etry phase: [/]"
                    ).strip().lower()

                    if choice in ("s", "skip"):
                        console.print("  [dim]Skipping remaining phases.[/]")
                        # Mark remaining as skipped
                        for remaining_key in selected_phases[i:]:
                            remaining_cls = phase_map[remaining_key]
                            phase_results.append((
                                remaining_key,
                                remaining_cls.name if hasattr(remaining_cls, 'name') else remaining_key,
                                "⊘", "skipped", "User skipped"
                            ))
                        break
                    elif choice in ("r", "retry"):
                        console.print("  [cyan]Retrying phase...[/]")
                        phase2 = phase_cls(
                            runner=runner,
                            logger=logger,
                            config=config,
                            system=system_info,
                        )
                        results2 = phase2.run()
                        for k in total_commands:
                            total_commands[k] += results2.get(k, 0)
                        # Update the last result
                        if results2.get("failed", 0) == 0:
                            phase_results[-1] = (
                                phase_key, phase.name, phase.icon, "passed (retry)",
                                f"{results2['passed']} steps"
                            )
                        else:
                            phase_results[-1] = (
                                phase_key, phase.name, phase.icon, "partial (retry)",
                                f"{results2['passed']} passed, {results2['failed']} failed"
                            )
                    # else: continue (default)

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted by user. Stopping.[/]")
            phase_results.append((
                phase_key, phase.name, phase.icon, "interrupted", ""
            ))
            break
        except Exception as e:
            logger.error(f"Phase '{phase_key}' crashed", str(e))
            phase_results.append((
                phase_key, phase.name, phase.icon, "error", str(e)[:80]
            ))

    # ── Detailed Summary ──
    _print_summary(phase_results, total_commands, logger)

    show_completion()


def _print_summary(
    phase_results: list[tuple],
    total_commands: dict,
    logger: ForgeLogger,
):
    """Print a detailed summary table of all phase results."""
    from rich import box
    from rich.table import Table

    console.print()
    console.rule("[bold]Setup Summary", style="white")
    console.print()

    table = Table(
        box=box.ROUNDED,
        border_style="blue",
        padding=(0, 1),
        show_header=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Phase", style="white", min_width=25)
    table.add_column("Status", min_width=15)
    table.add_column("Details", style="dim", min_width=20)

    passed_phases = 0
    failed_phases = 0
    skipped_phases = 0

    for i, (_key, name, icon, status, details) in enumerate(phase_results, 1):
        if status in ("passed", "passed (retry)"):
            status_display = f"[green]✓ {status}[/]"
            passed_phases += 1
        elif status in ("partial", "partial (retry)"):
            status_display = f"[yellow]◐ {status}[/]"
            failed_phases += 1
        elif status == "skipped":
            status_display = "[dim]⊘ skipped[/]"
            skipped_phases += 1
        elif status == "interrupted":
            status_display = "[yellow]⊗ interrupted[/]"
            failed_phases += 1
        else:
            status_display = f"[red]✗ {status}[/]"
            failed_phases += 1

        table.add_row(str(i), f"{icon} {name}", status_display, details)

    console.print(table)

    # Command-level stats
    console.print()
    console.print("  [bold]Phases:[/]  ", end="")
    parts = []
    if passed_phases:
        parts.append(f"[green]{passed_phases} passed[/]")
    if failed_phases:
        parts.append(f"[yellow]{failed_phases} with issues[/]")
    if skipped_phases:
        parts.append(f"[dim]{skipped_phases} skipped[/]")
    console.print("  ".join(parts))

    console.print("  [bold]Steps:[/]   ", end="")
    parts = []
    if total_commands["passed"]:
        parts.append(f"[green]{total_commands['passed']} passed[/]")
    if total_commands["failed"]:
        parts.append(f"[red]{total_commands['failed']} failed[/]")
    if total_commands["skipped"]:
        parts.append(f"[dim]{total_commands['skipped']} skipped[/]")
    console.print("  ".join(parts))

    console.print(f"\n  [dim]Full log: {logger.log_file}[/]")
    console.print()


if __name__ == "__main__":
    main()
