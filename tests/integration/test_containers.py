"""Real installs inside throwaway containers for every supported family.

Run with:  pytest -m integration tests/integration -v
Needs podman or docker and network access. Each image takes a few minutes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "/src/tests/integration/container-check.sh"
IMAGES = os.environ.get(
    "DISTROFORGE_IMAGES",
    "docker.io/library/ubuntu:24.04 docker.io/library/debian:12 "
    "registry.fedoraproject.org/fedora:44 docker.io/library/archlinux:latest",
).split()

ENGINE = shutil.which("podman") or shutil.which("docker")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(ENGINE is None, reason="podman or docker is required"),
]


@pytest.mark.parametrize("image", IMAGES)
def test_real_install_in_container(image: str) -> None:
    assert ENGINE is not None
    result = subprocess.run(
        [ENGINE, "run", "--rm", "-v", f"{ROOT}:/src:ro,z", image, "bash", SCRIPT],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    log = result.stdout + result.stderr
    assert result.returncode == 0, log[-6000:]
    assert "ALL CHECKS PASSED" in log
