"""
DistroForge - Distro Adapters
Abstraction layer for distro-specific packager managment commands.
"""

from abc import ABC, abstractmethod

class DistroAdapter(ABC):
    """Base class for distro-sepcific commands"""
    
    @abstractmethod
    def update(self) -> str:
        """Return the system update command."""
        pass
        @abstractmethod
    def install(self, *packages: str) -> str:
        """Return the install command for given packages."""
        pass
    
    @abstractmethod
    def install_flatpak(self, app_id: str) -> str:
        """Return flatpak install command."""
        pass
    
    @abstractmethod
    def add_repo(self, name: str, repo_url: str, key_url: str = "") -> list[tuple[str, str]]:
        """Return commands to add a third-party repository."""
        pass
    
    @abstractmethod
    def upgrade(self) -> str:
        """Return the full system upgrade command."""
        pass
    
class UbuntuAdapter(DistroAdapter):
    """Adapter for Ubuntu, Pop!_OS, Mint, and other Debian-based distros."""
    
    def update(self) -> str:
        return "sudo apt update"
    
    def install(self, *packages: str) -> str:
        pkgs = " ".join(packages)
        return f"sudo apt install -y {pkgs}"
    
    def install_flatpak(self, app_id: str) -> str:
        return f"flatpak install -y flathub {app_id}"
    
    def add_repo(self, name, repo_url, key_url = "") -> list[tuple[str, str]]:
        """
        Add a third-party apt repository.
        Returns list of (comman, description) tuple.
        """
        commands = []
        if key_url:
            commands.append((
                f"wget -qO- {key_url} | gpg --dearmor | "
                f"sudo tee /etc/apt/keyrings/{name}.gpg > /dev/null",
                f"Add GPG key for {name}",
            ))
            commands.append((
                f'echo "deb [arch=$(dpkg --print-architecture) '
                f'signed-by=/etc/apt/keyrings/{name}.gpg] {repo_url}" | '
                f"sudo tee /etc/apt/sources.list.d/{name}.list > /dev/null",
                f"Add repository for {name}",
            ))
        else:
            commands.append((
                f"sudo add-apt-repository -y {repo_url}",
                f"Add repository for {name}",
            ))
        commands.append(("sudo apt update", f"Update package lists after adding {name}"))
        return commands
    
    def upgrade(self) -> str:
        return "sudo apt update && sudo apt full-upgrade -y"
    
    
class FedoraAdapter(DistroAdapter):
    """Adapter for Fedora, Nobara, and other RPM-based distros. (Stub)"""
    
    def update(self) -> str:
        return "sudo dnf check-update"
    
    def install(self, *packages: str) -> str:
        pkgs = " ".join(packages)
        return f"sudo dnf install -y {pkgs}"

    def install_flatpak(self, app_id: str) -> str:
        return f"flatpak install -y flathub {app_id}"

    def add_repo(self, name: str, repo_url: str, key_url: str = "") -> list[tuple[str, str]]:
        commands = []
        if key_url:
            commands.append((
                f"sudo rpm --import {key_url}",
                f"Import GPG key for {name}",
            ))
        commands.append((
            f"sudo dnf config-manager --add-repo {repo_url}",
            f"Add repository for {name}",
        ))
        return commands

    def upgrade(self) -> str:
        return "sudo dnf upgrade -y"
    
    
def get_adapter(family: str) -> DistroAdapter:
    """Factory: return the correct adapter for the distro family."""
    adapters = {
        "ubuntu": UbuntuAdapter,
        "fedora": FedoraAdapter
    }
    adapter_cls = adapters.get(family)
    if adapter_cls is None:
        raise ValueError(f"Unsupported distro family: {family}. Supprted: {list(adapters.keys())}")
    return adapter_cls()