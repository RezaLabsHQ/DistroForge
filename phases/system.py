"""
DistroForge — System Phase
System updates, essential packages, GPU driver verification.
"""

from phases import Phase
from distros import get_adapter


class SystemPhase(Phase):
    name = "System Foundation"
    description = "Updates, essential packages, GPU driver verification"
    icon = "🖥️"

    def execute(self):
        adapter = get_adapter(self.system.distro_family.value)

        # ── Full system upgrade ──
        self.step("Running full system upgrade")
        self.cmd(adapter.upgrade(), description="System upgrade")

        # ── Install essential packages ──
        self.step("Installing essential system packages")
        essentials = self.cfg("system", "essentials", default=[])
        if essentials:
            self.cmd(
                adapter.install(*essentials),
                description=f"Install {len(essentials)} essential packages",
                timeout=300,
            )

        # ── GPU driver verification ──
        self.step("Verifying GPU driver")
        gpu = self.system.gpu_vendor.value

        if gpu == "nvidia":
            if self.installed("nvidia-smi"):
                result = self.runner.run("nvidia-smi --query-gpu=name,driver_version --format=csv,noheader")
                if result.success:
                    self.logger.success(f"Nvidia driver active: {result.stdout}")
                else:
                    self.logger.warning("nvidia-smi found but query failed — driver may need reboot")
            else:
                self.logger.warning(
                    "Nvidia GPU detected but nvidia-smi not found. "
                    "You may need to install drivers manually."
                )
        elif gpu == "amd":
            self.logger.success("AMD GPU — using open-source mesa drivers (built into kernel)")
        elif gpu == "intel":
            self.logger.success("Intel GPU — using open-source i915 driver (built into kernel)")
        else:
            self.logger.warning("GPU vendor not detected — skipping driver check")

        # ── Ensure Flatpak + Flathub are available ──
        self.step("Ensuring Flatpak is available")
        if not self.installed("flatpak"):
            self.cmd(adapter.install("flatpak"), description="Install Flatpak")
            self.cmd(
                "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
                description="Add Flathub repository",
            )
        else:
            self.logger.info("Flatpak already installed")
            self.cmd(
                "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
                description="Ensure Flathub repository is added",
            )