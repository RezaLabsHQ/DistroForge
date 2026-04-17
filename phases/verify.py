"""
DistroForge — Verification Phase
Runs post-setup health checks to confirm everything was installed correctly.
"""

from rich import box
from rich.console import Console
from rich.table import Table

from core.detector import GpuVendor
from phases import Phase

console = Console()


class VerifyPhase(Phase):
    name = "Verification"
    description = "Post-setup health checks and version report"
    icon = "🔍"

    def execute(self):
        checks = []

        # ── System ──
        self.step("Checking system tools")
        checks.extend(self._check_tools([
            ("git", "git"),
            ("curl", "curl"),
            ("wget", "wget"),
            ("htop", "htop"),
            ("btop", "btop"),
            ("neofetch", "neofetch"),
            ("ssh", "ssh"),
        ]))

        # ── Shell ──
        self.step("Checking shell setup")
        checks.extend(self._check_tools([
            ("zsh", "zsh"),
            ("starship", "starship"),
        ]))

        # Check Oh My Zsh directory
        home = self.system.home_dir
        omz = self.runner.run(f"test -d {home}/.oh-my-zsh", check=False)
        checks.append(("Oh My Zsh", "installed" if omz.success else "missing", omz.success))

        # ── GPU ──
        self.step("Checking GPU driver")
        if self.system.gpu_vendor == GpuVendor.NVIDIA:
            nvidia = self.runner.get_version("nvidia-smi", flag="--query-gpu=driver_version --format=csv,noheader")
            if nvidia:
                checks.append(("Nvidia Driver", nvidia, True))
            else:
                checks.append(("Nvidia Driver", "not detected", False))
        elif self.system.gpu_vendor == GpuVendor.AMD:
            checks.append(("AMD GPU", "mesa (kernel)", True))
        elif self.system.gpu_vendor == GpuVendor.INTEL:
            checks.append(("Intel GPU", "i915 (kernel)", True))

        # ── Development Tools ──
        self.step("Checking development environment")

        # Node
        node_ver = self._get_tool_version_with_env("node")
        checks.append(("Node.js", node_ver or "not installed", bool(node_ver)))

        npm_ver = self._get_tool_version_with_env("npm")
        checks.append(("npm", npm_ver or "not installed", bool(npm_ver)))

        # Python (via pyenv)
        python_ver = self._get_tool_version_with_env("python")
        checks.append(("Python", python_ver or "not installed", bool(python_ver)))

        # Docker
        docker_ver = self.runner.get_version("docker")
        checks.append(("Docker", docker_ver or "not installed", bool(docker_ver)))

        # Docker group check
        groups = self.runner.get_output("groups")
        docker_group = "docker" in groups
        checks.append(("Docker (user group)", "member" if docker_group else "not in group — reboot needed", docker_group))

        # GitHub CLI
        gh_ver = self.runner.get_version("gh")
        checks.append(("GitHub CLI", gh_ver or "not installed", bool(gh_ver)))

        # VS Code
        code_ver = self.runner.get_version("code")
        checks.append(("VS Code", code_ver or "not installed", bool(code_ver)))

        # ── Languages ──
        self.step("Checking language runtimes")
        lang_checks = [
            ("rustc", "Rust"),
            ("go", "Go"),
            ("java", "Java"),
            ("dotnet", ".NET"),
        ]
        for binary, name in lang_checks:
            ver = self.runner.get_version(binary)
            if ver:
                checks.append((name, ver, True))
            elif self.cfg("dev", "languages", binary.replace("rustc", "rust"), default=False):
                checks.append((name, "not installed (configured)", False))
            # Skip if not configured — don't clutter the report

        # ── Gaming ──
        if self.cfg("gaming", "enabled", default=True):
            self.step("Checking gaming layer")
            gaming_checks = [
                ("steam", "Steam"),
                ("gamemoderun", "Gamemode"),
                ("mangohud", "MangoHud"),
            ]
            for binary, name in gaming_checks:
                installed = self.runner.check_installed(binary)
                checks.append((name, "installed" if installed else "not installed", installed))

        # ── Peripherals ──
        self.step("Checking peripherals")
        periph_checks = [
            ("openrgb", "OpenRGB"),
            ("solaar", "Solaar"),
            ("piper", "Piper"),
        ]
        for binary, name in periph_checks:
            if self.cfg("peripherals", binary, default=False):
                installed = self.runner.check_installed(binary)
                checks.append((name, "installed" if installed else "not installed", installed))

        # ── System Services ──
        self.step("Checking system services")

        # Firewall
        ufw = self.runner.run("sudo ufw status 2>/dev/null | head -1", check=False)
        if ufw.success and "active" in ufw.stdout.lower():
            checks.append(("Firewall (UFW)", "active", True))
        else:
            checks.append(("Firewall (UFW)", "inactive", False))

        # SSD trim
        trim = self.runner.run("systemctl is-enabled fstrim.timer 2>/dev/null", check=False)
        trim_ok = trim.success and "enabled" in trim.stdout.lower()
        checks.append(("SSD TRIM Timer", "enabled" if trim_ok else "disabled", trim_ok))

        # ── SSH Key ──
        ssh_key = self.runner.run(f"test -f {home}/.ssh/id_ed25519", check=False)
        checks.append(("SSH Key", "present" if ssh_key.success else "missing", ssh_key.success))

        # ── Flatpak ──
        flatpak_ok = self.runner.check_installed("flatpak")
        checks.append(("Flatpak", "installed" if flatpak_ok else "missing", flatpak_ok))

        # ── Render the report ──
        self._render_report(checks)

    def _check_tools(self, tools: list[tuple[str, str]]) -> list[tuple[str, str, bool]]:
        """Check a list of (binary, display_name) and return results."""
        results = []
        for binary, name in tools:
            installed = self.runner.check_installed(binary)
            ver = ""
            if installed:
                ver = self.runner.get_version(binary) or "installed"
            results.append((name, ver if installed else "missing", installed))
        return results

    def _get_tool_version_with_env(self, tool: str) -> str:
        """
        Get version of tools that may require sourced shell environments
        (fnm, pyenv, etc.) — try direct first, then with common env paths.
        """
        # Try direct first
        ver = self.runner.get_version(tool)
        if ver:
            return ver

        # Try with fnm env (for node/npm)
        home = self.system.home_dir
        fnm_result = self.runner.run(
            f'export PATH="{home}/.local/share/fnm:{home}/.fnm:$PATH" && '
            f'eval "$(fnm env 2>/dev/null)" && {tool} --version 2>/dev/null | head -1',
            check=False,
        )
        if fnm_result.success and fnm_result.stdout:
            return fnm_result.stdout.strip()

        # Try with pyenv (for python)
        pyenv_result = self.runner.run(
            f'export PYENV_ROOT="{home}/.pyenv" && '
            f'export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH" && '
            f'{tool} --version 2>/dev/null | head -1',
            check=False,
        )
        if pyenv_result.success and pyenv_result.stdout:
            return pyenv_result.stdout.strip()

        return ""

    def _render_report(self, checks: list[tuple[str, str, bool]]):
        """Render a pretty verification report table."""
        console.print()

        table = Table(
            title="[bold]Verification Report",
            box=box.ROUNDED,
            border_style="blue",
            padding=(0, 1),
        )
        table.add_column("Component", style="white", min_width=20)
        table.add_column("Status", style="white", min_width=30)
        table.add_column("", width=3)

        passed = 0
        failed = 0

        for name, status, ok in checks:
            icon = "[green]✓[/]" if ok else "[red]✗[/]"
            status_style = "green" if ok else "red"
            table.add_row(name, f"[{status_style}]{status}[/]", icon)
            if ok:
                passed += 1
            else:
                failed += 1

        console.print(table)
        console.print()
        console.print(
            f"  [green]{passed} passed[/]  "
            f"{'[red]' + str(failed) + ' failed[/]' if failed else ''}"
        )
        console.print()

        if failed == 0:
            self.logger.success("All checks passed")
        else:
            self.logger.warning(f"{failed} check(s) need attention")
