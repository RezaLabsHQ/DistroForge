"""
DistroForge - Distro & Hardware Detector
Identifies the current linux distribution, GPU vendor, and system capbilites
"""

import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class DistroFamily(Enum):
    """Distro enum"""
    UBUNTU = "ubuntu"
    FEDORA = "fedora"
    ARCH = "arch"
    UNKNOWN = "unknown"

class GpuVendor(Enum):
    """
    CPU vendors
    Currently all gpu providers are:
    nvidia, amd, intel
    """
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    UNKNOWN = "unknown"
    
@dataclass
class SystemInfo:
    """Complete system information snapshot."""
    distro_id: str = ""
    distro_name: str = ""
    distro_version: str = ""
    distro_codename: str = ""
    distro_family: DistroFamily = DistroFamily.UNKNOWN #Default 
    package_manager: str = ""
    
    gpu_vendor: GpuVendor = GpuVendor.UNKNOWN #Default
    gpu_name: str = ""
    gpu_driver: str = ""
    
    cpu_name: str = ""
    ram_gb: int = 0
    hostname: str = ""
    username: str = ""
    home_dir: str = ""
    shell: str  = ""
    
    #Default Window manager and package manager
    is_wayland: bool = False
    has_flatpak: bool = False
    has_snap: bool = False
  
    
def _run(cmd: str) -> str:
    """Run a shell command and return stripped stdout, or empty string on failure."""
    try:
        result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, Exception):
        return ""

    
def _read_file(path: str) -> str:
    """Read a file and return contens, or empty string if missing."""
    try:
        return Path(path).read_text().strip()
    except (FileNotFoundError, PermissionError):
        return ""


def detect_distro() -> tuple[str, str, str, str, DistroFamily, str]:
    """Detect Linux distribution details from /etc/os-release."""
    os_release = _read_file("/etc/os-release")
    
    distro_id = ""
    distro_name = ""
    distro_version = ""
    distro_codename = ""
    
    for line in os_release.splitlines():
        if line.startswith("ID="):
            distro_id = line.split("=", 1)[1].strip('"').lower()
        elif line.startswith("NAME="):
            distro_name = line.split("=", 1)[1].strip('"')
        elif line.startswith("VERSION_ID="):
            distro_version = line.split("=", 1)[1].strip('"')
        elif line.startswith("VERSION_CODENAME="):
            distro_codename = line.split("=", 1)[1].strip('"')
            
    # Also check ID_LIKE for family detection
    id_like = ""
    for line in os_release.splitlines():
        if line.startswith("ID_LIKE="):
            id_like = line.split("=", 1)[1].strip('"').lower()
            
    # Determine family
    ubuntu_ids = {"ubuntu", "pop", "linuxmint", "elementary", "zorin", "neon"}
    fedora_ids = {"fedora", "nobara", "ultramarine"}
    arch_ids = {"arch", "manjaro", "endeavouros", "garuda", "cachyos"}
    
    if distro_id in ubuntu_ids or "ubuntu" in id_like or "debian" in id_like:
        family = DistroFamily.UBUNTU
        pkg_mgr = "apt"
    elif distro_id in fedora_ids or "fedora" in id_like:
        family = DistroFamily.FEDORA
        pkg_mgr = "dnf"
    elif distro_id in arch_ids or "arch" in id_like:
        family = DistroFamily.ARCH
        pkg_mgr = "pacman"
    else:
        family = DistroFamily.UNKNOWN
        pkg_mgr = "unknown"
        
    return distro_id, distro_name, distro_version, distro_codename, family, pkg_mgr
        
def detect_gpu() -> tuple[GpuVendor, str, str]:
    """Detect GPU vendor and model via lspci"""
    lspci = _run("lspci | grep -iE 'vga|3d|display'") # Run Command
    
    if not lspci:
        return GpuVendor.UNKNOWN, "unkown", ""
    
    lspci_lower = lspci.lower()
    
    if "nvidia" in lspci_lower:
        vendor = GpuVendor.NVIDIA
        # Try to get driver version
        driver = _run("nvidia-smi --query-gpu=driver_version --formate=csv,noheader 2>/dev/null") # Run command to check nvidia driver first
    elif "amd" in lspci_lower or "radeon" in lspci_lower:
        vendor = GpuVendor.AMD
        driver = "mesa (open-source)" # Don't need to install later
    elif "intel" in lspci_lower:
        vendor = GpuVendor.INTEL
        driver = "i915 (open-source)" # Don't need to install later
    else:
        vendor = GpuVendor.UNKNOWN
        driver = ""
    
    # Extract GPU model name
    match = re.search(r':\s+(.+?)$', lspci.split('\n')[0])
    gpu_name = match.group(1) if match else lspci.split('\n')[0]
    
    return vendor, gpu_name, driver

def detect_cpu() -> str:
    """Detect CPU model name."""
    cpuinfo = _read_file("/proc/cpuinfo")
    for line in cpuinfo.splitlines():
        if "model name" in line.lower():
            return line.split(":", 1)[1].strip()
    return "Unknown CPU"


def detect_ram() -> str:
    """Detect total RAM in GB"""
    meminfo = _read_file("/proc/meminfo")
    for line in meminfo.splitlines():
        if line.startswith("MemTotal"):
            kb = int(re.search(r'(\d+)', line).group(1))
            return round(kb / 1024 / 1024)
    return 0


def detect_system() -> SystemInfo:
    """Run full system detection and return a SystemInfo dataclase."""
    distro_id, distro_name, distro_version, distro_codename, family, pkg_mgr = detect_distro()
    gpu_vendor, gpu_name, gpu_driver = detect_gpu()
    
    info = SystemInfo(
        distro_id=distro_id,
        distro_name=distro_name,
        distro_version=distro_version,
        distro_codename=distro_codename,
        distro_family=family,
        package_manager=pkg_mgr,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        gpu_driver=gpu_driver,
        cpu_name=detect_cpu(),
        ram_gb=detect_ram(),
        hostname=_run("hostname"),
        username=_run("whoami"),
        home_dir=_run("echo $HOME"),
        shell=_run("echo $SHELL"),
        is_wayland="wayland" in _run("echo $XDG_SESSION_TYPE").lower(),
        has_flatpak=bool(_run("which flatpak")),
        has_snap=bool(_run("which snap")),
    )
    
    return info