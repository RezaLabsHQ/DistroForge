"""
DistroForge - Logging System
Structured logging to both console (via Rich) and log files
"""

import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console

console = Console()


class ForgeLogger:
    """
    Dual-output logger: pretty console via Rich + detailed file log.
    """

    def __init__(self, log_dir: str | None = None, verbose: bool = False):
        self.verbose = verbose

        if log_dir is None:
            log_dir = Path.home() / ".distroforge" / "logs"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%d%m%Y_%H%M%S")
        log_file = log_dir / f"distroforge_{timestamp}.log"

        self.file_logger = logging.getLogger("distroforge")
        self.file_logger.setLevel(logging.DEBUG)

        if not self.file_logger.handlers:
            fh = logging.FileHandler(log_file)
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
            fh.setFormatter(fmt)
            self.file_logger.addHandler(fh)

        self.log_file = log_file

    def phase(self, name: str, description: str = ""):
        """Log the start of a setup phase."""
        msg = f"Phase: {name}"
        if description:
            msg += f" - {description}"
        console.print()
        console.rule(f"[bold cyan]{name}[/]", style="cyan")
        if description:
            console.print(f" [dim]{description}[/]")
        console.print()
        self.file_logger.info(msg)

    def step(self, message: str):
        """Log a step within a phase."""
        console.print(f" [bold yellow]->[/] {message}")

    def command(self, description: str):
        """Log that a command is about to run."""
        console.print(f" [dim]⚙ {description}[/]") #Use this symbol for commands: ⚙
        self.file_logger.debug(f" Command: {description}")

    def success(self, message: str, duration: float = 0.0):
        """Log a successful operation."""
        dur = f" [dim]({duration:.1f}s)[/]" if duration > 0 else ""
        console.print(f" [bold green]✓[/] {message}{dur}") # Corrent Operation symbol (tick) ✓
        self.file_logger.info(f" ✓ {message} ({duration:.1f}s)")

    def error(self, message: str, detail: str = ""):
        """Log an error."""
        console.print(f" [bold red]✗ {message}[/]") # Error cross symbol ✗
        if detail:
            for line in detail.splitlines()[:5]:
                console.print(f"    [dim red]{line}[/]")
        self.file_logger.error(f" ✗ {message}: {detail}")

    def warning(self, message: str):
        """Log a warning."""
        console.print(f" [bold yellow]⚠ {message}[/]") # Warning symbol ⚠
        self.file_logger.warning(f" ⚠ {message}")

    def info(self, message: str):
        """Log an informational message."""
        console.print(f" [dim]{message}[/]")
        self.file_logger.info(f" {message}")

    def verbose_output(self, output: str):
        """Log verbose command output (only shown with --version flag)."""
        self.file_logger.debug(f" Output: {output}")
        if self.verbose:
            for line in output.splitlines()[:30]:
                console.print(f"    [dim white]| {line}[/]")
            if len(output.splitlines()) > 30:
                remaining = len(output.splitlines()) - 30
                console.print(f"    [dim]| ... ({remaining} more lines in log file)[/]")

    def skip(self, message: str):
        """Log a skipped step."""
        console.print(f" [dim]⊘ {message} (skipped)[/]") # Unkown symbol for skipped step ⊘
        self.file_logger.info(f" ⊘ Skipped: {message}")

    def dry_run(self, description: str, command: str):
        """Log a dry-run command (not executed.)"""
        console.print(f" [bold magenta]⊡ DRY RUN:[/] {description}") # Symbol for not exectued command ⊡
        console.print(f"    [dim]{command}[/]")
        self.file_logger.info(f" DRY RUN: {description} -> {command}")

    def retry(self, message: str, attempt: int, max_attempts: int, reason: str = ""):
        """Log a retry attempt."""
        console.print(f" [yellow]↻ Retry {attempt}/{max_attempts}: {message}[/] ") # Retry symbol ↻
        if reason:
            console.print(f"    [dim]{reason}[/]")
        self.file_logger.warning(f" ↻ Retry {attempt}/{max_attempts}: {message} - {reason}")

    def summary(self, total: int, passed: int, faild: int, skipped: int):
        """Print a final summary."""
        console.print()
        console.rule("[bold]Setup Summary", style="white")
        console.print(f" Total phases: {total}")
        console.print(f" [green]Passed: {passed}[/]")
        if faild:
            console.print(f" [red]Faild: {faild}[/]")
        if skipped:
            console.print(f" [dim]Skipped: {skipped}[/]")
        console.print(f"\n [dim]Full log: {self.log_file}[/]")
        console.print()
