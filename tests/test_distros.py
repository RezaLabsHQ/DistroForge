"""
Tests for distro adapters — package manager command generation.
"""

import pytest

from distros import FedoraAdapter, UbuntuAdapter, get_adapter


class TestUbuntuAdapter:
    """Tests for Ubuntu/Debian package commands."""

    def setup_method(self):
        self.adapter = UbuntuAdapter()

    def test_update(self):
        assert self.adapter.update() == "sudo apt update"

    def test_upgrade(self):
        cmd = self.adapter.upgrade()
        assert "apt update" in cmd
        assert "full-upgrade" in cmd
        assert "-y" in cmd

    def test_install_single(self):
        cmd = self.adapter.install("git")
        assert cmd == "sudo apt install -y git"

    def test_install_multiple(self):
        cmd = self.adapter.install("git", "curl", "wget")
        assert cmd == "sudo apt install -y git curl wget"

    def test_install_flatpak(self):
        cmd = self.adapter.install_flatpak("com.brave.Browser")
        assert "flatpak install" in cmd
        assert "flathub" in cmd
        assert "com.brave.Browser" in cmd

    def test_add_repo_with_key(self):
        commands = self.adapter.add_repo(
            "docker",
            "https://download.docker.com/linux/ubuntu noble stable",
            "https://download.docker.com/linux/ubuntu/gpg",
        )
        assert len(commands) == 3  # key, repo, update
        assert "gpg" in commands[0][0]
        assert "docker" in commands[1][0]
        assert "apt update" in commands[2][0]

    def test_add_repo_without_key(self):
        commands = self.adapter.add_repo("ppa", "ppa:some/ppa")
        assert len(commands) == 2  # add-apt-repository, update
        assert "add-apt-repository" in commands[0][0]


class TestFedoraAdapter:
    """Tests for Fedora/RPM package commands."""

    def setup_method(self):
        self.adapter = FedoraAdapter()

    def test_update(self):
        assert self.adapter.update() == "sudo dnf check-update"

    def test_upgrade(self):
        cmd = self.adapter.upgrade()
        assert "dnf upgrade" in cmd
        assert "-y" in cmd

    def test_install_single(self):
        cmd = self.adapter.install("git")
        assert cmd == "sudo dnf install -y git"

    def test_install_multiple(self):
        cmd = self.adapter.install("git", "curl", "wget")
        assert cmd == "sudo dnf install -y git curl wget"

    def test_install_flatpak(self):
        cmd = self.adapter.install_flatpak("com.brave.Browser")
        assert "flatpak install" in cmd
        assert "flathub" in cmd

    def test_add_repo_with_key(self):
        commands = self.adapter.add_repo(
            "docker",
            "https://download.docker.com/linux/fedora/docker-ce.repo",
            "https://download.docker.com/linux/fedora/gpg",
        )
        assert len(commands) == 2  # import key, add repo
        assert "rpm --import" in commands[0][0]


class TestGetAdapter:
    """Tests for the adapter factory function."""

    def test_get_ubuntu_adapter(self):
        adapter = get_adapter("ubuntu")
        assert isinstance(adapter, UbuntuAdapter)

    def test_get_fedora_adapter(self):
        adapter = get_adapter("fedora")
        assert isinstance(adapter, FedoraAdapter)

    def test_unsupported_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            get_adapter("gentoo")

    def test_unsupported_shows_available(self):
        with pytest.raises(ValueError, match="ubuntu"):
            get_adapter("solus")
