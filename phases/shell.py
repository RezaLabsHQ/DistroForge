"""
DistroForge — Shell Phase
Installs and configures zsh, Oh My Zsh, Starship prompt, and plugins.
"""

from distros import get_adapter
from phases import Phase


class ShellPhase(Phase):
    name = "Shell Setup"
    description = "zsh, Oh My Zsh, Starship prompt, plugins"
    icon = "🐚"

    def execute(self):
        adapter = get_adapter(self.system.distro_family.value)
        shell_cfg = self.cfg("shell", default={})
        default_shell = shell_cfg.get("default", "zsh")

        if default_shell != "zsh":
            self.logger.info(f"Shell set to '{default_shell}' — skipping zsh setup")
            return

        # ── Install zsh ──
        self.step("Installing zsh")
        if not self.installed("zsh"):
            self.cmd(adapter.install("zsh"), description="Install zsh")
        else:
            self.logger.info("zsh already installed")

        # ── Set zsh as default shell ──
        self.step("Setting zsh as default shell")
        current_shell = self.runner.get_output("echo $SHELL")
        if "zsh" not in current_shell:
            self.cmd(
                "chsh -s $(which zsh)",
                description="Change default shell to zsh",
            )
        else:
            self.logger.info("zsh is already the default shell")

        # ── Install Oh My Zsh ──
        if shell_cfg.get("oh_my_zsh", True):
            self.step("Installing Oh My Zsh")
            home = self.system.home_dir
            if not self.runner.run(f"test -d {home}/.oh-my-zsh", check=False).success:
                self.cmd(
                    'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended',
                    description="Install Oh My Zsh (unattended)",
                )
            else:
                self.logger.info("Oh My Zsh already installed")

            # ── Install third-party plugins ──
            self.step("Installing zsh plugins")
            plugins = shell_cfg.get("plugins", [])
            custom_dir = f"{home}/.oh-my-zsh/custom/plugins"

            third_party = {
                "zsh-autosuggestions": "https://github.com/zsh-users/zsh-autosuggestions",
                "zsh-syntax-highlighting": "https://github.com/zsh-users/zsh-syntax-highlighting.git",
            }

            for plugin_name, repo_url in third_party.items():
                if plugin_name in plugins:
                    plugin_dir = f"{custom_dir}/{plugin_name}"
                    if not self.runner.run(f"test -d {plugin_dir}", check=False).success:
                        self.cmd(
                            f"git clone {repo_url} {plugin_dir}",
                            description=f"Install plugin: {plugin_name}",
                        )
                    else:
                        self.logger.info(f"Plugin '{plugin_name}' already installed")

            # ── Configure plugins in .zshrc ──
            self.step("Configuring .zshrc plugins")
            plugin_str = " ".join(plugins)
            zshrc = f"{home}/.zshrc"

            # Replace the plugins=(...) line
            self.cmd(
                f"""sed -i 's/^plugins=(.*/plugins=({plugin_str})/' {zshrc}""",
                description="Set plugins in .zshrc",
            )

        # ── Install Starship prompt ──
        prompt = shell_cfg.get("prompt", "starship")
        if prompt == "starship":
            self.step("Installing Starship prompt")
            if not self.installed("starship"):
                self.cmd(
                    "curl -sS https://starship.rs/install.sh | sh -s -- -y",
                    description="Install Starship",
                )
            else:
                self.logger.info("Starship already installed")

            # Add to zshrc if not present
            home = self.system.home_dir
            zshrc = f"{home}/.zshrc"
            self.cmd(
                f"""grep -q 'starship init zsh' {zshrc} || echo 'eval "$(starship init zsh)"' >> {zshrc}""",
                description="Add Starship to .zshrc",
            )

        # ── Extra zshrc lines ──
        extra_lines = shell_cfg.get("extra_zshrc_lines", [])
        if extra_lines:
            self.step("Adding extra .zshrc configuration")
            home = self.system.home_dir
            zshrc = f"{home}/.zshrc"
            for line in extra_lines:
                self.cmd(
                    f"""grep -qF '{line}' {zshrc} || echo '{line}' >> {zshrc}""",
                    description=f"Add: {line}",
                )
