"""
DistroForge - Terminal UI Components
Rich-based interactive terminal interface
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from core.detector import SystemInfo, DistroFamily, GpuVendor

console = Console()

BANNER = r"""
    ____  _      __             ______
   / __ \(_)____/ /__________  / ____/___  _________ ____
  / / / / / ___/ __/ ___/ __ \/ /_  / __ \/ ___/ __ `/ _ \
 / /_/ / (__  ) /_/ /  / /_/ / __/ / /_/ / /  / /_/ /  __/
/_____/_/____/\__/_/   \____/_/    \____/_/   \__, /\___/
                                             /____/
"""

VERSION = "1.0.0"

def show_banner():
    """Display the DistroForge banner."""
    console.print(
        Panel(
            Text(BANNER, style="bold cyan", justify="center"),
            subtitle = f"[dim]v{VERSION} - by Hamid at Reza Labs HQ[/]",
            border_style = "cyan",
            box = box.DOUBLE,
            padding = (0,2),
        )
    )
    console.print()
    
def show_system_info(info: SystemInfo):
    """Display detected system information in a table."""
    table = Table(
        title="[bold]System Detected",
        box=box.ROUNDED,
        border_style="blue",
        show_header=False,
        padding=(0,2)
    )
    table.add_column("Property", style="bold white", min_width=18)
    table.add_column("Value", style="white")
    
    #Distro info
    distro_colour = {
        DistroFamily.UBUNTU: "yellow",
        DistroFamily.FEDORA: "blue",
        DistroFamily.ARCH: "cyan",
    }.get(info.distro_family, "white")
    
    table.add_row("Distro", f"[{distro_colour}]{info.distro_name} {info.distro_version}[/]")
    table.add_row("Family" f"[{distro_colour}]{info.distro_family.value.title()}[/]-based")
    table.add_row("Package Manger", info.package_manager)
    table.add_row("", "")
    
    #Hardware info
    gpu_colour = {
        GpuVendor.NVIDIA: "green",
        GpuVendor.AMD: "red",
        GpuVendor.INTEL: "blue"
    }.get(info.gpu_vendor, "white")
    
    gpu_display = info.gpu_name[:60] if info.gpu_name else "Unkown"
    if info.gpu_driver:
        gpu_display += f" [dim](driver: {info.gpu_driver})[/]"
    
    table.add_row("CPU", info.cpu_name[:60])
    table.add_row("GPU", f"[{gpu_colour}]{gpu_display}[/]")
    table.add_row("RAM", f"{info.ram_gb} GB")
    table.add_row("", "")
    
    # System info
    table.add_row("User", f"{info.username}@{info.hostname}")
    table.add_row("Home", info.home_dir)
    table.add_row("Display", "Wayland" if info.is_wayland else "X11")
    
    console.print(table)
    console.print()
    

def select_distro() -> str:
    """
    Interactie distro family selector.
    Returns the selected distro family key.
    """
    console.print("[bold]Select your distro family:[/]\n")
    
    options = [
        ("1", "Ubuntu-based", "Ubuntu, Pop!_OS, Mint, Elementary, Zorin", "yellow", True),
        ("2", "Fedora-based", "Fedora, Nobara, Ultramarine", "blue", False),
        ("3", "Arch-based", "Arch, Manjaro, EndeavourOS, CachyOS", "cyan", False),
    ]
    
    for key, name, desc, colour, available in options:
        status = "" if available else " [dim red](comming soon)[/]"
        console.print(
            f" [{colour}][bold][key][/bold][/{colour}] "
            f"[bold]{name}[/]{status}"
        )
        console.print(f"    [dim]{desc}[/]")
        console.print()
        
    while True:
        choice = console.input("[bold cyan] ▸ Enter choice (1-3): [/]").strip()
        
        if choice == "1":
            return "ubuntu"
        elif choice == "2":
            console.print(" [yellow]Fedora support comming soon. Stubbed for now.[/]")
            return "fedora"
        elif choice == "3":
            console.print(" [yellow]Arch suppprt is planned. Not yet available.[/]")
            continue
        else:
            console.print(" [red]Invalid choice. Try again.[/]")
            
    
def select_phase(available_phases: list[tuple[str, str]]) -> list[str]:
    """
    Let user select which phase to run.
    Returns list of selected phase keys.
    """
    console.print("[bold]Select setup phases:[/]\n")
    
    for i, (key, description) in enumerate(available_phases, 1):
        console.print(f" [cyan]{i}[/] {description} [dim]{key}[/]")
        
    console.print(f"\n [cyan]A[/] [bold]Run ALL phasse[/]")
    console.print()
    
    while True:
        choice = console.input("[bold cyan] ▸ Enter choice (e.g., 1,3,5 or A for all): [/]").strip().upper()
        
        if choice == "A":
            return [key for key, _ in available_phases]
        
        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            selected = []
            for idx in indices:
                if 1 <= idx <= len(available_phases):
                    selected.append(available_phases[idx - 1][0])
                else:
                    console.print(f"  [red]Invalid index: {idx}[/]")
                    continue
            if selected:
                return selected
        except ValueError:
            pass
        
        console.print("  [red]Invalid input. Use numbers separated by commas, or A.[/]")
        

def confirm_proceed(phases: list[str], dry_run: bool = False) -> bool:
    """Ask user to confirm before proceeding."""
    mode = "[magenta]DRY RUN[/]" if dry_run else "[green]LIVE[/]"
    
    console.print(f"\n  Mode: {mode}")
    console.print(f"  Phases: [cyan]{', '.join(phases)}[/]")
    console.print()
    
    response = console.input("  [bold]Proceed? (Y/n): [/]").strip().lower()
    return response in ("", "y", "yes")


def show_completion():
    """Display completion message."""
    console.print()
    console.print(
        Panel(
            "[bold green]Setup complete![/]\n\n"
            "[dim]Reboot recommended: [bold white]sudo reboot[/][/]\n"
            "[dim]Check logs at: [bold white]~/.distroforge/logs/[/][/]",
            title="[bold]DistroForge[/]",
            border_style="green",
            box=box.DOUBLE,
            padding=(1, 4),
        )
    )
    console.print()
    
    
