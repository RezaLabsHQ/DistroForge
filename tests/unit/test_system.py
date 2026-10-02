from pathlib import Path

import pytest

from distroforge.core.system import (
    Family,
    GpuVendor,
    OsRelease,
    SystemInfo,
    family_for,
    parse_cpu_model,
    parse_gpu,
    parse_meminfo_gb,
    parse_os_release,
)

OS_RELEASES = {
    "ubuntu": ('ID=ubuntu\nID_LIKE=debian\nVERSION_CODENAME=noble\nVERSION_ID="24.04"', Family.DEBIAN),
    "debian": ('ID=debian\nVERSION_CODENAME=bookworm\nVERSION_ID="12"', Family.DEBIAN),
    "mint": (
        'ID=linuxmint\nID_LIKE="ubuntu debian"\nUBUNTU_CODENAME=noble\nVERSION_CODENAME=wilma',
        Family.DEBIAN,
    ),
    "pop": ('ID=pop\nID_LIKE="ubuntu debian"\nUBUNTU_CODENAME=noble', Family.DEBIAN),
    "elementary": ("ID=elementary\nID_LIKE=ubuntu", Family.DEBIAN),
    "zorin": ('ID=zorin\nID_LIKE="ubuntu debian"', Family.DEBIAN),
    "kali": ("ID=kali\nID_LIKE=debian", Family.DEBIAN),
    "fedora": (
        'ID=fedora\nVERSION_ID=44\nPRETTY_NAME="Fedora Linux 44 (KDE Plasma Desktop Edition)"',
        Family.FEDORA,
    ),
    "nobara": ('ID=nobara\nID_LIKE="rhel centos fedora"', Family.FEDORA),
    "rocky": ('ID="rocky"\nID_LIKE="rhel centos fedora"', Family.FEDORA),
    "alma": ('ID="almalinux"\nID_LIKE="rhel centos fedora"', Family.FEDORA),
    "arch": ('ID=arch\nPRETTY_NAME="Arch Linux"', Family.ARCH),
    "manjaro": ("ID=manjaro\nID_LIKE=arch", Family.ARCH),
    "endeavouros": ("ID=endeavouros\nID_LIKE=arch", Family.ARCH),
    "cachyos": ("ID=cachyos\nID_LIKE=arch", Family.ARCH),
    "garuda": ("ID=garuda\nID_LIKE=arch", Family.ARCH),
    "opensuse": ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"', Family.UNKNOWN),
}


@pytest.mark.parametrize("name", sorted(OS_RELEASES))
def test_family_detection(name: str) -> None:
    text, expected = OS_RELEASES[name]
    assert family_for(parse_os_release(text), which=lambda _b: None) is expected


def test_family_falls_back_to_package_manager_binary() -> None:
    os_release = parse_os_release("ID=mystery")
    assert family_for(os_release, which=lambda b: "/usr/bin/dnf" if b == "dnf" else None) is Family.FEDORA


def test_os_release_parsing_handles_quotes_and_comments() -> None:
    os_release = parse_os_release(
        '# comment\nNAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\n\nBROKEN'
    )
    assert os_release.name == "Linux Mint"
    assert os_release.id_like == ("ubuntu", "debian")
    assert os_release.tokens == {"linuxmint", "ubuntu", "debian"}


def test_apt_placeholders_use_ubuntu_codename_on_derivatives(tmp_path: Path) -> None:
    mint = parse_os_release(OS_RELEASES["mint"][0])
    info = SystemInfo(os=mint, family=Family.DEBIAN, arch="x86_64", home=tmp_path, username="u")
    values = info.placeholders()
    assert values["codename"] == "noble"
    assert values["apt_os"] == "ubuntu"
    assert values["arch"] == "amd64"

    debian = SystemInfo(os=parse_os_release(OS_RELEASES["debian"][0]), family=Family.DEBIAN, arch="aarch64")
    assert debian.placeholders()["apt_os"] == "debian"
    assert debian.placeholders()["arch"] == "arm64"


def test_gpu_prefers_discrete_card() -> None:
    lspci = (
        "00:02.0 VGA compatible controller: Intel Corporation Raptor Lake-S GT1 [UHD Graphics 770]\n"
        "01:00.0 VGA compatible controller: NVIDIA Corporation AD104 [GeForce RTX 4070 SUPER] (rev a1)\n"
        "01:00.1 Audio device: NVIDIA Corporation AD104 High Definition Audio Controller\n"
    )
    vendor, name = parse_gpu(lspci)
    assert vendor is GpuVendor.NVIDIA
    assert name.startswith("NVIDIA Corporation AD104")


def test_gpu_unknown_when_no_display_device() -> None:
    assert parse_gpu("00:1f.3 Audio device: Intel") == (GpuVendor.UNKNOWN, "")


def test_meminfo_and_cpu_parsing() -> None:
    assert parse_meminfo_gb("MemTotal:       32768000 kB\nMemFree: 1 kB") == 31
    assert parse_meminfo_gb("garbage") == 0
    assert parse_cpu_model("processor: 0\nmodel name\t: AMD Ryzen 7 7800X3D\n") == "AMD Ryzen 7 7800X3D"


def test_with_family_returns_new_frozen_copy() -> None:
    info = SystemInfo(os=OsRelease(id="x"))
    changed = info.with_family(Family.ARCH)
    assert changed.family is Family.ARCH and info.family is Family.UNKNOWN
