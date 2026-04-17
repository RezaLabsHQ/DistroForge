"""
DistroForge — Apps Phase
Installs Flatpak applications, Nerd Fonts, and peripheral tools.
"""

from phases import Phase
from distros import get_adapter


class AppsPhase(Phase):
    name = "Applications & Fonts"
    description = "Flatpak apps, Nerd Fonts, peripheral tools"
    icon = "📦"

    def execute(self):
        adapter = get_adapter(self.system.distro_family.value)

        self._install_flatpak_apps(adapter)
        self._install_fonts()
        self._install_peripherals(adapter)

    def _install_flatpak_apps(self, adapter):
        """Install Flatpak applications from config."""
        apps = self.cfg("apps", "flatpak", default=[])
        if not apps:
            return

        self.step(f"Installing {len(apps)} Flatpak applications")
        for app_id in apps:
            app_name = app_id.split(".")[-1]
            self.cmd(
                adapter.install_flatpak(app_id),
                description=f"Install {app_name}",
            )

    def _install_fonts(self):
        """Install Nerd Fonts from config."""
        fonts = self.cfg("fonts", "nerd_fonts", default=[])
        if not fonts:
            return

        self.step(f"Installing {len(fonts)} Nerd Fonts")
        home = self.system.home_dir
        font_dir = f"{home}/.local/share/fonts"

        self.cmd(f"mkdir -p {font_dir}", description="Create fonts directory")

        for font_name in fonts:
            # Check if font is already installed
            check = self.runner.run(
                f"ls {font_dir}/{font_name}* 2>/dev/null | head -1",
                check=False,
            )
            if check.success and check.stdout:
                self.logger.info(f"Font '{font_name}' already installed")
                continue

            self.cmd(
                f"cd {font_dir} && "
                f"wget -q https://github.com/ryanoasis/nerd-fonts/releases/latest/download/{font_name}.zip && "
                f"unzip -o -q {font_name}.zip && "
                f"rm -f {font_name}.zip",
                description=f"Install {font_name} Nerd Font",
                timeout=120,
            )

        self.cmd("fc-cache -fv > /dev/null 2>&1", description="Rebuild font cache")

    def _install_peripherals(self, adapter):
        """Install peripheral management tools (OpenRGB, Solaar, Piper, etc.)."""
        periph_cfg = self.cfg("peripherals", default={})
        if not periph_cfg:
            return

        self.step("Installing peripheral tools")

        if periph_cfg.get("openrgb", False):
            if not self.installed("openrgb"):
                # Try Flatpak first (safer sandbox)
                self.cmd(
                    adapter.install_flatpak("org.openrgb.OpenRGB"),
                    description="Install OpenRGB via Flatpak",
                )
            else:
                self.logger.info("OpenRGB already installed")

        if periph_cfg.get("solaar", False):
            if not self.installed("solaar"):
                self.cmd(
                    adapter.install("solaar"),
                    description="Install Solaar (Logitech device manager)",
                )
            else:
                self.logger.info("Solaar already installed")

        if periph_cfg.get("piper", False):
            if not self.installed("piper"):
                self.cmd(
                    adapter.install("piper", "libratbag-tools"),
                    description="Install Piper + libratbag (gaming mouse config)",
                )
                self.cmd(
                    "sudo systemctl enable --now ratbagd",
                    description="Enable ratbagd daemon",
                )
            else:
                self.logger.info("Piper already installed")

        if periph_cfg.get("input_remapper", False):
            if not self.installed("input-remapper-gtk"):
                self.cmd(
                    adapter.install("input-remapper"),
                    description="Install input-remapper",
                )
            else:
                self.logger.info("input-remapper already installed")