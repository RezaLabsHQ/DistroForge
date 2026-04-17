"""
DistroForge — Gaming Phase
Installs Steam, Proton tools, Gamemode, MangoHud, and Lutris.
"""

from phases import Phase
from distros import get_adapter


class GamingPhase(Phase):
    name = "Gaming Layer"
    description = "Steam, Proton, Gamemode, MangoHud, Lutris"
    icon = "🎮"

    def should_skip(self) -> bool:
        return not self.cfg("gaming", "enabled", default=True)

    def execute(self):
        adapter = get_adapter(self.system.distro_family.value)
        gaming_cfg = self.cfg("gaming", default={})

        # ── Steam ──
        if gaming_cfg.get("steam", True):
            self.step("Installing Steam")
            if not self.installed("steam"):
                if self.system.distro_family.value == "ubuntu":
                    self.cmd(
                        adapter.install("steam-installer"),
                        description="Install Steam",
                    )
                elif self.system.distro_family.value == "fedora":
                    # Fedora needs RPM Fusion for Steam
                    self.cmd(
                        "sudo dnf install -y "
                        "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm "
                        "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm",
                        description="Enable RPM Fusion repositories",
                    )
                    self.cmd(
                        adapter.install("steam"),
                        description="Install Steam",
                    )
            else:
                self.logger.info("Steam already installed")

        # ── ProtonUp-Qt ──
        if gaming_cfg.get("protonup_qt", True):
            self.step("Installing ProtonUp-Qt (Proton version manager)")
            self.cmd(
                adapter.install_flatpak("net.davidotek.pupgui2"),
                description="Install ProtonUp-Qt via Flatpak",
            )

        # ── Gamemode ──
        if gaming_cfg.get("gamemode", True):
            self.step("Installing Gamemode (CPU performance optimizer)")
            self.cmd(
                adapter.install("gamemode"),
                description="Install Gamemode",
            )

        # ── MangoHud ──
        if gaming_cfg.get("mangohud", True):
            self.step("Installing MangoHud (performance overlay)")
            self.cmd(
                adapter.install("mangohud"),
                description="Install MangoHud",
            )

        # ── Lutris ──
        if gaming_cfg.get("lutris", True):
            self.step("Installing Lutris (non-Steam game manager)")
            self.cmd(
                adapter.install_flatpak("net.lutris.Lutris"),
                description="Install Lutris via Flatpak",
            )

        # ── Steam library path info ──
        lib_path = gaming_cfg.get("steam_library_path")
        if lib_path:
            self.logger.info(
                f"Remember to add '{lib_path}' as a Steam library folder in "
                f"Steam → Settings → Storage → Add Drive"
            )