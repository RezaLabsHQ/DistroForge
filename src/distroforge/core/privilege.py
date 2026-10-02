"""sudo credential handling.

DistroForge never sees or stores a password. Credentials are validated once by
``sudo -v`` on the real terminal (the TUI suspends itself for this), then kept
fresh with ``sudo -n -v`` while a plan runs. Every root command uses
``sudo -n`` so it fails fast instead of hanging if the credentials expire.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import subprocess

from distroforge.core.logging import get_logger

log = get_logger("sudo")

KEEPALIVE_SECONDS = 60


def sudo_available() -> bool:
    return shutil.which("sudo") is not None


def credentials_cached() -> bool:
    if not sudo_available():
        return False
    try:
        proc = subprocess.run(
            ["sudo", "-n", "-v"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def authenticate_interactive() -> bool:
    """Prompt for the sudo password on the controlling terminal."""
    if not sudo_available():
        return False
    if credentials_cached():
        return True
    print("\nDistroForge needs administrator rights for the selected tasks.")
    try:
        proc = subprocess.run(["sudo", "-v"], timeout=300, check=False)
    except (OSError, subprocess.SubprocessError, KeyboardInterrupt):
        return False
    log.info("sudo authentication %s", "succeeded" if proc.returncode == 0 else "failed")
    return proc.returncode == 0


async def keepalive(interval: float = KEEPALIVE_SECONDS) -> None:
    """Refresh the sudo timestamp until cancelled."""
    while True:
        await asyncio.sleep(interval)
        with contextlib.suppress(OSError):
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "-n",
                "-v",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
