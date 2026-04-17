"""
DistroForge — Quality of Life Phase
Firewall, SSD trim, swappiness, kernel modules, system tweaks.
"""

from phases import Phase


class QoLPhase(Phase):
    name = "Quality of Life"
    description = "Firewall, SSD trim, system tweaks"
    icon = "✨"

    def execute(self):
        qol_cfg = self.cfg("qol", default={})

        # ── Firewall ──
        if qol_cfg.get("firewall", True):
            self.step("Configuring firewall")
            if self.system.distro_family.value == "ubuntu":
                self.cmd("sudo ufw --force enable", description="Enable UFW firewall")
                self.cmd(
                    "sudo ufw default deny incoming",
                    description="Set default deny incoming",
                )
                self.cmd(
                    "sudo ufw default allow outgoing",
                    description="Set default allow outgoing",
                )
            elif self.system.distro_family.value == "fedora":
                self.cmd(
                    "sudo systemctl enable --now firewalld",
                    description="Enable firewalld",
                )

        # ── SSD TRIM ──
        if qol_cfg.get("ssd_trim", True):
            self.step("Enabling SSD TRIM timer")
            self.cmd(
                "sudo systemctl enable --now fstrim.timer",
                description="Enable weekly fstrim",
            )

        # ── Swappiness ──
        swappiness = qol_cfg.get("swappiness")
        if swappiness is not None:
            self.step(f"Setting swappiness to {swappiness}")
            self.cmd(
                f"sudo sysctl -w vm.swappiness={swappiness}",
                description=f"Set runtime swappiness to {swappiness}",
            )
            # Make persistent
            self.cmd(
                f"""grep -q 'vm.swappiness' /etc/sysctl.conf && """
                f"""sudo sed -i 's/^vm.swappiness=.*/vm.swappiness={swappiness}/' /etc/sysctl.conf || """
                f"""echo 'vm.swappiness={swappiness}' | sudo tee -a /etc/sysctl.conf""",
                description=f"Persist swappiness={swappiness} in sysctl.conf",
            )

        # ── i2c modules (for OpenRGB GPU/RAM detection) ──
        if self.cfg("peripherals", "openrgb", default=False):
            self.step("Loading i2c kernel modules for RGB detection")
            self.cmd("sudo modprobe i2c-dev", description="Load i2c-dev module")
            self.cmd(
                "grep -q 'i2c-dev' /etc/modules-load.d/openrgb.conf 2>/dev/null || "
                "echo 'i2c-dev' | sudo tee -a /etc/modules-load.d/openrgb.conf",
                description="Persist i2c-dev module",
            )

            # Add user to i2c and plugdev groups
            username = self.system.username
            self.cmd(
                f"sudo groupadd i2c 2>/dev/null || true && "
                f"sudo usermod -aG i2c,plugdev {username}",
                description="Add user to i2c and plugdev groups",
            )

        # ── Disable suspend on lid close for desktops (optional) ──
        # Only relevant if running on a desktop with no lid

        self.logger.info("Quality of life tweaks applied. Reboot recommended.")
