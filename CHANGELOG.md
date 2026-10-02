# Changelog

## 2.0.0 — 2026-10-02

DistroForge is now a full application rather than a set of setup scripts.

### Highlights

- **Full-screen terminal app** built with Textual: category sidebar, search, details pane, review screen showing every command, and live progress with streaming output.
- **You choose everything.** The hard-coded phases are replaced by a catalog of about 160 apps and tweaks. Every item can be selected individually, and its install method (distro package, Flatpak, AUR, upstream installer) can be changed per item.
- **Multi-distro.** Debian/Ubuntu (apt), Fedora/RHEL (dnf) and Arch (pacman + AUR), with Flatpak as the universal fallback. Derivatives are detected through `ID_LIKE`.
- **Profiles.** Essentials, Developer, Gaming, Creator, Security baseline and *Classic* (everything 1.x did), plus your own saved, shareable profiles.
- **Themes.** All four Catppuccin flavours, a new Forge brand theme, Tokyo Night, Nord, Gruvbox, Dracula, Rosé Pine and more.
- **App-menu integration** with a new logo. DistroForge opens in your terminal like btop. Includes bash/zsh/fish completions.
- **Scriptable CLI:** `list`, `apply`, `profiles`, `doctor`, `validate`, `integrate`.
- **Extensible.** Add or override apps with YAML in `~/.config/distroforge/catalog.d/`.

### Security

- Commands are argument vectors only; `shell=True` is banned and tested for.
- Strict validation of all catalog and settings data, HTTPS-only downloads, signed repositories, confined root writes, `sudo -n` with up-front authentication, and explicit acknowledgement before running remote scripts. See `SECURITY.md`.

### Fixed (from 1.x)

- Dry-run steps were counted as *passed* instead of *skipped*.
- pyenv `.zshrc` setup only ever added its first line.
- apt-only package names (`build-essential`, `golang-go`, `software-properties-common`) broke Fedora runs.
- `dnf check-update` exit code 100 was reported as a failure.
- Shell init lines were written to `.zshrc` even when zsh wasn't used.
- Predictable `/tmp` path when installing the Microsoft GPG key.
- Personal data (name, email, hostname) shipped in the default `config.yaml`.
- Version was defined in three places.

### Breaking changes

- `--phases` and `config.yaml` / `config.local.yaml` are gone. Use the app, `distroforge apply --profile …`, or a profile YAML file. `distroforge apply --profile classic` reproduces 1.x.
- Python package layout moved to `src/distroforge`, and the entry point is `distroforge.cli:main`.
- Logs moved from `~/.distroforge/logs` to `~/.local/state/distroforge/logs`.

## 1.0.0

Initial release: phase-based setup for Ubuntu and Fedora.
