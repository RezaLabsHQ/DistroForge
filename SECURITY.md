# Security model

DistroForge installs software and changes system settings, so it is designed to make doing the wrong thing hard.

## Execution

- **No shell, ever.** Every command is an argument vector executed with `subprocess`/`asyncio.create_subprocess_exec`. Catalog data cannot be interpreted as shell syntax, so `; rm -rf ~` in a package name is just an invalid package name. A test fails the build if `shell=True`, `os.system` or `os.popen` appears anywhere.
- **No option injection.** Every identifier (package, Flatpak ID, unit, group, module, font…) must match a strict allow-list pattern that cannot start with `-`.
- **Root only where needed.** DistroForge refuses to run as root. Steps that need privileges run as `sudo -n -- <argv>`: credentials are checked once up front, on your real terminal (the UI suspends itself), then kept fresh while the plan runs. `-n` guarantees a step can never hang on a hidden password prompt. DistroForge never sees your password.
- **Root writes are confined.** Files are only ever written as root inside `/etc/apt/keyrings`, `/etc/apt/sources.list.d`, `/etc/yum.repos.d`, `/etc/pki/rpm-gpg`, `/etc/sysctl.d` and `/etc/modules-load.d`. Content is staged in a private `0700` temp directory and moved into place with `install(1)`; predictable `/tmp` paths are never used.

## Network

- Downloads are **HTTPS only**, including redirects. They have size limits and an optional pinned SHA-256.
- Third-party repositories are added with their signing key in a dedicated keyring (`signed-by=` for apt, `gpgcheck=1` for dnf). Because their packages install as root, adding one is flagged on the Review screen and must be acknowledged, just like remote scripts and AUR packages.
- **Upstream install scripts** (`script:` methods) are the last-resort method. They are downloaded to a private directory (never piped from `curl` into a shell), run as your user (never root), and are always flagged on the Review screen. You must tick an acknowledgement before a live run.

## Files you own

- Shell startup files are edited only inside named, removable blocks (`# >>> distroforge:<id> >>>`). Edits are atomic and keep the file's permissions.
- Settings are stored with mode `0600`. Logs redact values that look like tokens or passwords.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Report a vulnerability) rather than a public issue.
