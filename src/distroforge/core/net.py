"""HTTPS downloads with size limits and optional checksum verification."""

from __future__ import annotations

import hashlib
import http.client
import os
import urllib.request
from pathlib import Path
from urllib.error import URLError

from distroforge import __version__
from distroforge.core.validate import ValidationError, check_https_url

USER_AGENT = f"DistroForge/{__version__} (+https://github.com/RezaLabsHQ/DistroForge)"


class DownloadError(RuntimeError):
    pass


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        try:
            check_https_url(newurl)
        except ValidationError as exc:
            raise DownloadError(f"Refusing redirect to {newurl}") from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpsOnlyRedirects())


def download(
    url: str,
    dest: Path,
    *,
    max_bytes: int = 50 * 1024 * 1024,
    sha256: str | None = None,
    timeout: float = 60.0,
) -> str:
    """Download ``url`` to ``dest`` (mode 0600). Returns the SHA-256 hex digest."""
    check_https_url(url)
    digest = hashlib.sha256()
    received = 0
    # Scheme is validated above (https only) and on every redirect.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out, _opener.open(request, timeout=timeout) as response:
            while chunk := response.read(64 * 1024):
                received += len(chunk)
                if received > max_bytes:
                    raise DownloadError(f"{url} is larger than {max_bytes // 1024 // 1024} MiB")
                digest.update(chunk)
                out.write(chunk)
    except (URLError, OSError, TimeoutError, http.client.HTTPException) as exc:
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {url}: {exc}") from exc
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise

    actual = digest.hexdigest()
    if sha256 and actual.lower() != sha256.lower():
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Checksum mismatch for {url}: expected {sha256}, got {actual}")
    return actual
