"""
DistroForge — Development Environment Phase
Installs Node.js, Python, Docker, Git config, GitHub CLI, editors, and language runtimes.
"""

from distros import get_adapter
from phases import Phase


class DevPhase(Phase):
    name = "Development Environment"
    description = "Node.js, Python, Docker, Git, editors, language runtimes"
    icon = "💻"

    def execute(self):
        adapter = get_adapter(self.system.distro_family.value)
        dev_cfg = self.cfg("dev", default={})
        home = self.system.home_dir

        self._setup_git()
        self._setup_editors(adapter)
        self._setup_node(dev_cfg, home)
        self._setup_python(dev_cfg, home)
        self._setup_docker(adapter, dev_cfg)
        self._setup_github_cli(adapter, dev_cfg, home)
        self._setup_languages(adapter, dev_cfg)

    def _setup_git(self):
        """Configure Git global settings."""
        self.step("Configuring Git")
        user_cfg = self.cfg("user", default={})

        git_settings = {
            "user.name": user_cfg.get("name", "Developer"),
            "user.email": user_cfg.get("email", "dev@example.com"),
            "init.defaultBranch": "main",
            "pull.rebase": "false",
            "core.editor": "nano",
        }

        for key, value in git_settings.items():
            self.cmd(
                f'git config --global {key} "{value}"',
                description=f"Set git {key}",
            )

    def _setup_editors(self, adapter):
        """Install code editors."""
        editors_cfg = self.cfg("editors", default={})

        if editors_cfg.get("vscode", False):
            self.step("Installing VS Code")
            if not self.installed("code"):
                if self.system.distro_family.value == "ubuntu":
                    self.cmd(
                        "wget -qO- https://packages.microsoft.com/keys/microsoft.asc | "
                        "gpg --dearmor > /tmp/packages.microsoft.gpg && "
                        "sudo install -D -o root -g root -m 644 /tmp/packages.microsoft.gpg "
                        "/etc/apt/keyrings/packages.microsoft.gpg",
                        description="Add Microsoft GPG key",
                    )
                    self.cmd(
                        'sudo sh -c \'echo "deb [arch=amd64,arm64,armhf '
                        'signed-by=/etc/apt/keyrings/packages.microsoft.gpg] '
                        'https://packages.microsoft.com/repos/code stable main" > '
                        '/etc/apt/sources.list.d/vscode.list\'',
                        description="Add VS Code repository",
                    )
                    self.cmd("sudo apt update", description="Update package lists")
                    self.cmd(
                        adapter.install("code"),
                        description="Install VS Code",
                    )
                elif self.system.distro_family.value == "fedora":
                    self.cmd(
                        "sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc",
                        description="Import Microsoft GPG key",
                    )
                    self.cmd(
                        'sudo sh -c \'echo -e "[code]\nname=Visual Studio Code\n'
                        'baseurl=https://packages.microsoft.com/yumrepos/vscode\n'
                        'enabled=1\ngpgcheck=1\n'
                        'gpgkey=https://packages.microsoft.com/keys/microsoft.asc" > '
                        '/etc/yum.repos.d/vscode.repo\'',
                        description="Add VS Code repository",
                    )
                    self.cmd(
                        adapter.install("code"),
                        description="Install VS Code",
                    )
            else:
                self.logger.info("VS Code already installed")

    def _setup_node(self, dev_cfg: dict, home: str):
        """Install Node.js via fnm or nvm."""
        node_cfg = dev_cfg.get("node", {})
        if not node_cfg:
            return

        manager = node_cfg.get("manager", "fnm")

        if manager == "fnm":
            self.step("Installing Node.js via fnm")
            if not self.installed("fnm"):
                self.cmd(
                    "curl -fsSL https://fnm.vercel.app/install | bash",
                    description="Install fnm",
                )
            else:
                self.logger.info("fnm already installed")

            # Ensure fnm is in zshrc
            zshrc = f"{home}/.zshrc"
            self.cmd(
                f"""grep -q 'fnm env' {zshrc} || echo 'eval "$(fnm env --use-on-cd --shell zsh)"' >> {zshrc}""",
                description="Add fnm to .zshrc",
            )

            # Install Node version using fnm
            fnm_path = f"{home}/.local/share/fnm"
            self.cmd(
                f'export PATH="{fnm_path}:$PATH" && eval "$(fnm env)" && '
                f"fnm install --lts && fnm default lts-latest",
                description="Install Node.js LTS via fnm",
            )

            # Install global packages
            global_pkgs = node_cfg.get("global_packages", [])
            if global_pkgs:
                self.step("Installing global npm packages")
                pkgs_str = " ".join(global_pkgs)
                self.cmd(
                    f'export PATH="{fnm_path}:$PATH" && eval "$(fnm env)" && '
                    f"npm install -g {pkgs_str}",
                    description=f"Install {len(global_pkgs)} global packages",
                )

    def _setup_python(self, dev_cfg: dict, home: str):
        """Install Python via pyenv."""
        py_cfg = dev_cfg.get("python", {})
        if not py_cfg:
            return

        manager = py_cfg.get("manager", "pyenv")

        if manager == "pyenv":
            self.step("Installing Python via pyenv")

            # Install build dependencies
            adapter = get_adapter(self.system.distro_family.value)
            build_deps = [
                "make", "build-essential", "libssl-dev", "zlib1g-dev",
                "libbz2-dev", "libreadline-dev", "libsqlite3-dev", "wget",
                "curl", "llvm", "libncurses-dev", "xz-utils", "tk-dev",
                "libxml2-dev", "libxmlsec1-dev", "libffi-dev", "liblzma-dev",
            ]
            self.cmd(
                adapter.install(*build_deps),
                description="Install Python build dependencies",
            )

            # Install pyenv
            pyenv_root = f"{home}/.pyenv"
            if not self.runner.run(f"test -d {pyenv_root}", check=False).success:
                self.cmd(
                    "curl https://pyenv.run | bash",
                    description="Install pyenv",
                )
            else:
                self.logger.info("pyenv already installed")

            # Add pyenv to zshrc
            zshrc = f"{home}/.zshrc"
            pyenv_lines = [
                'export PYENV_ROOT="$HOME/.pyenv"',
                '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"',
                'eval "$(pyenv init - zsh)"',
                'eval "$(pyenv virtualenv-init -)"',
            ]
            for line in pyenv_lines:
                self.cmd(
                    f"""grep -qF 'pyenv' {zshrc} || echo '{line}' >> {zshrc}""",
                    description="Add pyenv config to .zshrc",
                )

            # Install Python version
            version = py_cfg.get("version", "3.12")
            self.cmd(
                f'export PYENV_ROOT="{pyenv_root}" && export PATH="$PYENV_ROOT/bin:$PATH" && '
                f'eval "$(pyenv init -)" && '
                f"pyenv install -s {version} && pyenv global {version}",
                description=f"Install Python {version}",
                timeout=600,
            )

            # Install uv
            if py_cfg.get("install_uv", True):
                self.step("Installing uv (fast pip replacement)")
                self.cmd(
                    "curl -LsSf https://astral.sh/uv/install.sh | sh",
                    description="Install uv",
                )

    def _setup_docker(self, adapter, dev_cfg: dict):
        """Install Docker Engine + Compose."""
        if not dev_cfg.get("docker", False):
            return

        self.step("Installing Docker")
        if self.installed("docker"):
            self.logger.info("Docker already installed")
            return

        if self.system.distro_family.value == "ubuntu":
            # Remove old versions
            self.cmd(
                "sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true",
                description="Remove old Docker versions",
            )

            # Add Docker's official GPG key + repo
            codename = self.system.distro_codename or "noble"
            self.cmd(
                "sudo install -m 0755 -d /etc/apt/keyrings && "
                "sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg "
                "-o /etc/apt/keyrings/docker.asc && "
                "sudo chmod a+r /etc/apt/keyrings/docker.asc",
                description="Add Docker GPG key",
            )
            self.cmd(
                f'echo "deb [arch=$(dpkg --print-architecture) '
                f'signed-by=/etc/apt/keyrings/docker.asc] '
                f'https://download.docker.com/linux/ubuntu {codename} stable" | '
                f"sudo tee /etc/apt/sources.list.d/docker.list > /dev/null",
                description="Add Docker repository",
            )
            self.cmd("sudo apt update", description="Update package lists")
            self.cmd(
                adapter.install(
                    "docker-ce", "docker-ce-cli", "containerd.io",
                    "docker-buildx-plugin", "docker-compose-plugin",
                ),
                description="Install Docker Engine + Compose",
            )

        elif self.system.distro_family.value == "fedora":
            self.cmd(
                "sudo dnf config-manager --add-repo "
                "https://download.docker.com/linux/fedora/docker-ce.repo",
                description="Add Docker repository",
            )
            self.cmd(
                adapter.install(
                    "docker-ce", "docker-ce-cli", "containerd.io",
                    "docker-buildx-plugin", "docker-compose-plugin",
                ),
                description="Install Docker Engine + Compose",
            )

        # Add user to docker group
        self.cmd(
            "sudo groupadd docker 2>/dev/null || true",
            description="Create docker group",
        )
        username = self.system.username
        self.cmd(
            f"sudo usermod -aG docker {username}",
            description="Add user to docker group",
        )
        self.logger.info("Docker group change requires reboot to take effect")

    def _setup_github_cli(self, adapter, dev_cfg: dict, home: str):
        """Install GitHub CLI and generate SSH keys."""
        if not dev_cfg.get("github_cli", False):
            return

        self.step("Installing GitHub CLI")
        if not self.installed("gh"):
            if self.system.distro_family.value == "ubuntu":
                self.cmd(
                    "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | "
                    "sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && "
                    "sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && "
                    'echo "deb [arch=$(dpkg --print-architecture) '
                    'signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] '
                    'https://cli.github.com/packages stable main" | '
                    "sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && "
                    "sudo apt update && sudo apt install -y gh",
                    description="Install GitHub CLI",
                )
            elif self.system.distro_family.value == "fedora":
                self.cmd(
                    adapter.install("gh"),
                    description="Install GitHub CLI",
                )
        else:
            self.logger.info("GitHub CLI already installed")

        # Generate SSH key
        self.step("Setting up SSH key for GitHub")
        user_cfg = self.cfg("user", default={})
        ssh_comment = user_cfg.get("ssh_key_comment", "distroforge")
        ssh_key = f"{home}/.ssh/id_ed25519"

        if not self.runner.run(f"test -f {ssh_key}", check=False).success:
            self.cmd(
                f'ssh-keygen -t ed25519 -C "{ssh_comment}" -f {ssh_key} -N ""',
                description="Generate ED25519 SSH key",
            )
            self.logger.info(
                "SSH key generated. Run 'gh auth login' to upload to GitHub."
            )
        else:
            self.logger.info("SSH key already exists")

    def _setup_languages(self, adapter, dev_cfg: dict):
        """Install additional language runtimes."""
        langs = dev_cfg.get("languages", {})
        if not langs:
            return

        self.step("Installing additional language runtimes")

        if langs.get("rust", False):
            if not self.installed("rustc"):
                self.cmd(
                    "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                    description="Install Rust via rustup",
                )
            else:
                self.logger.info("Rust already installed")

        if langs.get("go", False):
            if not self.installed("go"):
                self.cmd(adapter.install("golang-go"), description="Install Go")
            else:
                self.logger.info("Go already installed")

        if langs.get("java", False):
            if not self.installed("java"):
                pkg = "java-21-openjdk-devel" if self.system.distro_family.value == "fedora" else "openjdk-21-jdk"
                self.cmd(adapter.install(pkg), description="Install OpenJDK 21")
            else:
                self.logger.info("Java already installed")

        if langs.get("dotnet", False):
            if not self.installed("dotnet"):
                pkg = "dotnet-sdk-8.0"
                self.cmd(adapter.install(pkg), description="Install .NET SDK 8.0")
            else:
                self.logger.info(".NET already installed")
