"""Distro and hardware detection.

Detection never invokes a shell: it reads ``/etc/os-release`` and ``/proc`` and
runs fixed argv probes. The result is an immutable :class:`SystemInfo`.
"""

from __future__ import annotations

import os
import platform
import pwd
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path


class Family(str, Enum):
    """Package-manager family. This is the only axis distro support varies on."""

    DEBIAN = "debian"
    FEDORA = "fedora"
    ARCH = "arch"
    UNKNOWN = "unknown"

    @property
    def package_manager(self) -> str:
        return _FAMILY_PM[self]

    @property
    def label(self) -> str:
        return _FAMILY_LABEL[self]


_FAMILY_PM = {
    Family.DEBIAN: "apt",
    Family.FEDORA: "dnf",
    Family.ARCH: "pacman",
    Family.UNKNOWN: "unknown",
}

_FAMILY_LABEL = {
    Family.DEBIAN: "Debian / Ubuntu",
    Family.FEDORA: "Fedora / RHEL",
    Family.ARCH: "Arch",
    Family.UNKNOWN: "Unknown",
}

# Distro IDs and ID_LIKE tokens that map to each family.
_FAMILY_MARKERS: dict[Family, frozenset[str]] = {
    Family.DEBIAN: frozenset(
        {"debian", "ubuntu", "pop", "linuxmint", "elementary", "zorin", "neon", "kali", "raspbian"}
    ),
    Family.FEDORA: frozenset(
        {"fedora", "nobara", "ultramarine", "rhel", "centos", "rocky", "almalinux", "bazzite"}
    ),
    Family.ARCH: frozenset({"arch", "manjaro", "endeavouros", "garuda", "cachyos", "artix", "arcolinux"}),
}

# Fallback when os-release is unhelpful: the package manager binary present.
_PM_BINARIES = (("apt-get", Family.DEBIAN), ("dnf", Family.FEDORA), ("pacman", Family.ARCH))

AUR_HELPERS = ("paru", "yay")


class GpuVendor(str, Enum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OsRelease:
    id: str = ""
    id_like: tuple[str, ...] = ()
    name: str = ""
    pretty_name: str = ""
    version_id: str = ""
    codename: str = ""
    ubuntu_codename: str = ""

    @property
    def tokens(self) -> frozenset[str]:
        return frozenset({self.id, *self.id_like} - {""})


@dataclass(frozen=True)
class SystemInfo:
    os: OsRelease = field(default_factory=OsRelease)
    family: Family = Family.UNKNOWN
    arch: str = ""
    kernel: str = ""
    cpu: str = ""
    ram_gb: int = 0
    gpu_vendor: GpuVendor = GpuVendor.UNKNOWN
    gpu_name: str = ""
    hostname: str = ""
    username: str = ""
    home: Path = field(default_factory=Path.home)
    login_shell: str = ""
    desktop: str = ""
    session_type: str = ""
    is_root: bool = False
    has_flatpak: bool = False
    aur_helper: str = ""

    @property
    def distro_name(self) -> str:
        return self.os.pretty_name or self.os.name or self.os.id or "Unknown Linux"

    @property
    def package_manager(self) -> str:
        return self.family.package_manager

    @property
    def apt_os(self) -> str:
        """Upstream apt repos (Docker, …) publish separate ``ubuntu`` and ``debian`` trees."""
        return "ubuntu" if "ubuntu" in self.os.tokens else "debian"

    @property
    def apt_codename(self) -> str:
        # Mint/Pop/elementary expose their own codename; upstream repos want Ubuntu's.
        return self.os.ubuntu_codename or self.os.codename

    @property
    def deb_arch(self) -> str:
        return {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"}.get(self.arch, self.arch)

    def placeholders(self) -> dict[str, str]:
        """Values catalog entries may reference as ``{name}``."""
        return {
            "home": str(self.home),
            "user": self.username,
            "arch": self.deb_arch if self.family is Family.DEBIAN else self.arch,
            "codename": self.apt_codename,
            "apt_os": self.apt_os,
            "version_id": self.os.version_id,
        }

    def with_family(self, family: Family) -> SystemInfo:
        return replace(self, family=family)


# ── Parsing ─────────────────────────────────────────


def parse_os_release(text: str) -> OsRelease:
    """Parse os-release(5) content. Values may be quoted with shell rules."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        try:
            parts = shlex.split(value)
        except ValueError:
            parts = [value.strip("\"'")]
        values[key.strip()] = parts[0] if parts else ""

    return OsRelease(
        id=values.get("ID", "").lower(),
        id_like=tuple(values.get("ID_LIKE", "").lower().split()),
        name=values.get("NAME", ""),
        pretty_name=values.get("PRETTY_NAME", ""),
        version_id=values.get("VERSION_ID", ""),
        codename=values.get("VERSION_CODENAME", ""),
        ubuntu_codename=values.get("UBUNTU_CODENAME", ""),
    )


def family_for(os_release: OsRelease, which: Callable[[str], str | None] = shutil.which) -> Family:
    """Map os-release to a family, preferring ID over ID_LIKE over binaries."""
    for family, markers in _FAMILY_MARKERS.items():
        if os_release.id in markers:
            return family
    for family, markers in _FAMILY_MARKERS.items():
        if markers.intersection(os_release.id_like):
            return family
    for binary, family in _PM_BINARIES:
        if which(binary):
            return family
    return Family.UNKNOWN


def parse_meminfo_gb(text: str) -> int:
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return round(int(parts[1]) / 1024 / 1024)
    return 0


def parse_cpu_model(text: str) -> str:
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() in ("model name", "hardware", "cpu model"):
            return value.strip()
    return ""


def parse_gpu(lspci_output: str) -> tuple[GpuVendor, str]:
    """Pick the most capable GPU from ``lspci`` output (discrete beats integrated)."""
    gpus = [
        line
        for line in lspci_output.splitlines()
        if any(tag in line.lower() for tag in ("vga compatible", "3d controller", "display controller"))
    ]
    if not gpus:
        return GpuVendor.UNKNOWN, ""

    def vendor_of(line: str) -> GpuVendor:
        lowered = line.lower()
        if "nvidia" in lowered:
            return GpuVendor.NVIDIA
        if "amd" in lowered or "radeon" in lowered or "ati " in lowered:
            return GpuVendor.AMD
        if "intel" in lowered:
            return GpuVendor.INTEL
        return GpuVendor.UNKNOWN

    priority = [GpuVendor.NVIDIA, GpuVendor.AMD, GpuVendor.INTEL, GpuVendor.UNKNOWN]
    best = min(gpus, key=lambda line: priority.index(vendor_of(line)))
    name = best.split(": ", 1)[1].strip() if ": " in best else best.strip()
    return vendor_of(best), name


# ── Live probes ─────────────────────────────────────


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _probe(argv: list[str]) -> str:
    if not shutil.which(argv[0]):
        return ""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=10, check=False, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def detect_system() -> SystemInfo:
    os_release = parse_os_release(_read("/etc/os-release") or _read("/usr/lib/os-release"))
    gpu_vendor, gpu_name = parse_gpu(_probe(["lspci"]))
    uname = platform.uname()
    euid = os.geteuid()
    try:
        entry = pwd.getpwuid(euid)
        username, home, login_shell = entry.pw_name, Path(entry.pw_dir), entry.pw_shell
    except KeyError:
        username, home, login_shell = os.environ.get("USER", ""), Path.home(), ""

    return SystemInfo(
        os=os_release,
        family=family_for(os_release),
        arch=uname.machine,
        kernel=uname.release,
        cpu=parse_cpu_model(_read("/proc/cpuinfo")) or uname.processor,
        ram_gb=parse_meminfo_gb(_read("/proc/meminfo")),
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        hostname=uname.node,
        username=username,
        home=home,
        login_shell=login_shell,
        desktop=os.environ.get("XDG_CURRENT_DESKTOP", ""),
        session_type=os.environ.get("XDG_SESSION_TYPE", ""),
        is_root=euid == 0,
        has_flatpak=shutil.which("flatpak") is not None,
        aur_helper=next((h for h in AUR_HELPERS if shutil.which(h)), ""),
    )
