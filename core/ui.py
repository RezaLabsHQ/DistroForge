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
    Console.print(
        Panel(
            Text(BANNER, style="bold cyan", justify="center"),
            subtitle = f"[dim]v{VERSION} - by Hamid at Reza Labs HQ[/]",
            border_style = "cyan",
            box = box.DOUBLE,
            padding = (0,2),
        )
    )
    Console.print()
    
