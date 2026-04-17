"""
Tests for core.detector — distro and hardware detection.
"""

import pytest
from unittest.mock import patch, mock_open
from core.detector import (
    detect_distro,
    detect_gpu,
    detect_cpu,
    detect_ram,
    detect_system,
    DistroFamily,
    GpuVendor,
    SystemInfo,
)


# ── Distro Detection ──────────────────────────────────


class TestDetectDistro:
    """Tests for distro family detection from /etc/os-release."""

    def _mock_os_release(self, content: str):
        return patch("core.detector._read_file", return_value=content)

    def test_detects_ubuntu(self):
        os_release = (
            'ID=ubuntu\nNAME="Ubuntu"\n'
            'VERSION_ID="24.04"\nVERSION_CODENAME=noble\n'
            'ID_LIKE=debian\n'
        )
        with self._mock_os_release(os_release):
            _, name, version, codename, family, pkg = detect_distro()
            assert family == DistroFamily.UBUNTU
            assert pkg == "apt"
            assert name == "Ubuntu"
            assert version == "24.04"
            assert codename == "noble"

    def test_detects_pop_os(self):
        os_release = (
            'ID=pop\nNAME="Pop!_OS"\n'
            'VERSION_ID="24.04"\nVERSION_CODENAME=noble\n'
            'ID_LIKE="ubuntu debian"\n'
        )
        with self._mock_os_release(os_release):
            distro_id, name, _, _, family, pkg = detect_distro()
            assert distro_id == "pop"
            assert family == DistroFamily.UBUNTU
            assert pkg == "apt"

    def test_detects_linux_mint(self):
        os_release = (
            'ID=linuxmint\nNAME="Linux Mint"\n'
            'VERSION_ID="22"\nVERSION_CODENAME=wilma\n'
            'ID_LIKE="ubuntu debian"\n'
        )
        with self._mock_os_release(os_release):
            _, _, _, _, family, pkg = detect_distro()
            assert family == DistroFamily.UBUNTU
            assert pkg == "apt"

    def test_detects_fedora(self):
        os_release = (
            'ID=fedora\nNAME="Fedora Linux"\n'
            'VERSION_ID="41"\nVERSION_CODENAME=""\n'
        )
        with self._mock_os_release(os_release):
            _, _, _, _, family, pkg = detect_distro()
            assert family == DistroFamily.FEDORA
            assert pkg == "dnf"

    def test_detects_nobara(self):
        os_release = (
            'ID=nobara\nNAME="Nobara Linux"\n'
            'VERSION_ID="40"\n'
            'ID_LIKE=fedora\n'
        )
        with self._mock_os_release(os_release):
            _, _, _, _, family, pkg = detect_distro()
            assert family == DistroFamily.FEDORA
            assert pkg == "dnf"

    def test_detects_arch(self):
        os_release = 'ID=arch\nNAME="Arch Linux"\n'
        with self._mock_os_release(os_release):
            _, _, _, _, family, pkg = detect_distro()
            assert family == DistroFamily.ARCH
            assert pkg == "pacman"

    def test_detects_manjaro_via_id_like(self):
        os_release = (
            'ID=manjaro\nNAME="Manjaro Linux"\n'
            'ID_LIKE=arch\n'
        )
        with self._mock_os_release(os_release):
            _, _, _, _, family, _ = detect_distro()
            assert family == DistroFamily.ARCH

    def test_unknown_distro(self):
        os_release = 'ID=gentoo\nNAME="Gentoo"\n'
        with self._mock_os_release(os_release):
            _, _, _, _, family, pkg = detect_distro()
            assert family == DistroFamily.UNKNOWN
            assert pkg == "unknown"

    def test_empty_os_release(self):
        with self._mock_os_release(""):
            _, _, _, _, family, _ = detect_distro()
            assert family == DistroFamily.UNKNOWN


# ── GPU Detection ─────────────────────────────────────


class TestDetectGpu:
    """Tests for GPU vendor detection from lspci."""

    def test_detects_nvidia(self):
        lspci = "01:00.0 VGA compatible controller: NVIDIA Corporation GA104 [GeForce RTX 4070 SUPER]"
        with patch("core.detector._run", return_value=lspci):
            vendor, name, _ = detect_gpu()
            assert vendor == GpuVendor.NVIDIA
            assert "NVIDIA" in name or "GeForce" in name

    def test_detects_amd(self):
        lspci = "06:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XT]"
        with patch("core.detector._run", return_value=lspci):
            vendor, _, driver = detect_gpu()
            assert vendor == GpuVendor.AMD
            assert "mesa" in driver.lower()

    def test_detects_intel(self):
        lspci = "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 770"
        with patch("core.detector._run", return_value=lspci):
            vendor, _, driver = detect_gpu()
            assert vendor == GpuVendor.INTEL
            assert "i915" in driver.lower()

    def test_no_gpu_found(self):
        with patch("core.detector._run", return_value=""):
            vendor, _, _ = detect_gpu()
            assert vendor == GpuVendor.UNKNOWN


# ── CPU Detection ─────────────────────────────────────


class TestDetectCpu:
    """Tests for CPU model detection from /proc/cpuinfo."""

    def test_detects_cpu_model(self):
        cpuinfo = (
            "processor\t: 0\n"
            "model name\t: AMD Ryzen 5 7600X 6-Core Processor\n"
            "cpu MHz\t\t: 4700.000\n"
        )
        with patch("core.detector._read_file", return_value=cpuinfo):
            cpu = detect_cpu()
            assert "Ryzen 5 7600X" in cpu

    def test_empty_cpuinfo(self):
        with patch("core.detector._read_file", return_value=""):
            cpu = detect_cpu()
            assert cpu == "Unknown CPU"


# ── RAM Detection ─────────────────────────────────────


class TestDetectRam:
    """Tests for RAM size detection from /proc/meminfo."""

    def test_detects_32gb(self):
        meminfo = "MemTotal:       32768000 kB\nMemFree:         1000000 kB\n"
        with patch("core.detector._read_file", return_value=meminfo):
            ram = detect_ram()
            assert ram == 31  # 32768000 kB ≈ 31 GB (integer division)

    def test_detects_16gb(self):
        meminfo = "MemTotal:       16384000 kB\n"
        with patch("core.detector._read_file", return_value=meminfo):
            ram = detect_ram()
            assert ram == 16

    def test_empty_meminfo(self):
        with patch("core.detector._read_file", return_value=""):
            ram = detect_ram()
            assert ram == 0


# ── SystemInfo ────────────────────────────────────────


class TestSystemInfo:
    """Tests for the SystemInfo dataclass."""

    def test_default_values(self):
        info = SystemInfo()
        assert info.distro_family == DistroFamily.UNKNOWN
        assert info.gpu_vendor == GpuVendor.UNKNOWN
        assert info.ram_gb == 0
        assert info.is_wayland is False

    def test_custom_values(self):
        info = SystemInfo(
            distro_id="pop",
            distro_name="Pop!_OS",
            distro_family=DistroFamily.UBUNTU,
            gpu_vendor=GpuVendor.NVIDIA,
            ram_gb=32,
        )
        assert info.distro_id == "pop"
        assert info.distro_family == DistroFamily.UBUNTU
        assert info.gpu_vendor == GpuVendor.NVIDIA