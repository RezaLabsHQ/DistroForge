# DistroForge

<div align="center">

```
██████╗ ██╗███████╗████████╗██████╗  ██████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
 ██╔══██╗██║██╔════╝╚══██╔══╝██╔══██╗██╔═══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
 ██║  ██║██║███████╗   ██║   ██████╔╝██║   ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗
 ██║  ██║██║╚════██║   ██║   ██╔══██╗██║   ██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
 ██████╔╝██║███████║   ██║   ██║  ██║╚██████╔╝██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
 ╚═════╝ ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

**A professional terminal-based Linux distro setup automation tool.**

</div>

DistroForge automates the complete setup of a fresh Linux installation — from system updates and driver verification to dev environment, gaming layer, and quality-of-life configuration. One command, fully configured machine.

Built by Hamid at [Reza Labs HQ](https://github.com/rezalabshq)

## Supported Distros

- [x] Ubuntu-based (Ubuntu, Pop!\_OS, Linux Mint, Elementary OS, Zorin)
- [x] Fedora-based (Fedora, Nobara) — _adapter ready, testing in progress_
- [ ] Arch-based (Arch, Manjaro, EndeavourOS) — _planned_

## Installation

### Recommended — one-liner

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/rezalabshq/DistroForge/main/install.sh)
```

This clones the repo to `~/.local/share/distroforge`, creates an isolated Python environment, installs dependencies, and drops a `distroforge` launcher into `~/.local/bin`. Your shell config is updated automatically if needed.

After install, open a new terminal (or `source ~/.zshrc`) and run:

```bash
distroforge --list
```

### Update

Re-run the same one-liner — it pulls the latest changes and rebuilds the environment.

### Alternative — pipx

```bash
pipx install git+https://github.com/rezalabshq/DistroForge.git
```

### Alternative — manual clone

```bash
git clone https://github.com/rezalabshq/DistroForge.git
cd DistroForge
pip install -r requirements.txt
python3 distroforge.py
```

## Usage

```bash
distroforge                            # Interactive mode (choose phases)
distroforge --list                     # Show all available phases
distroforge --phases system,shell,dev  # Run specific phases
distroforge --dry-run --yes            # Preview everything without changing anything
distroforge --phases verify            # Health check — see what's installed
distroforge --verbose                  # Show full command output
distroforge --yes                      # Skip confirmation prompts
distroforge --config my-setup.yaml    # Use a custom config file
distroforge --distro fedora            # Override distro detection
```

## Available Phases

| Phase    | What it does                                                                |
| -------- | --------------------------------------------------------------------------- |
| `system` | System updates, essential packages, GPU driver verification                 |
| `shell`  | zsh, Oh My Zsh, Starship prompt, plugins                                    |
| `dev`    | Node.js (fnm), Python (pyenv), Docker, Git, VS Code, Rust, Go, Java, .NET   |
| `gaming` | Steam, Proton, ProtonUp-Qt, Gamemode, MangoHud, Lutris                      |
| `apps`   | Flatpak applications, Nerd Fonts, peripheral tools (OpenRGB, Solaar, Piper) |
| `qol`    | Firewall (UFW), SSD trim, swappiness tuning, i2c modules                    |
| `verify` | Post-setup health check — version report of everything installed            |

## Configuration

All preferences live in `config.yaml`. Create `config.local.yaml` for personal overrides — it's gitignored and merges on top of the template.

```bash
cp config.yaml config.local.yaml
nano config.local.yaml
```

Config merge priority (highest wins): `--config <path>` > `config.local.yaml` > `config.yaml`

### Example: Minimal local override

```yaml
# config.local.yaml
user:
  name: "Hamid"
  email: "hamid@rezalabs.com"

gaming:
  enabled: false

dev:
  languages:
    rust: false
```

## Architecture

```
distro-forge/
├── distroforge.py          # Entry point + CLI
├── config.yaml             # Template config (committed)
├── pyproject.toml          # Python packaging + tool config
├── core/
│   ├── detector.py         # Distro & hardware auto-detection
│   ├── runner.py           # Command execution (logging, retries, dry-run)
│   ├── logger.py           # Dual-output logging (Rich console + file)
│   └── ui.py               # Terminal UI (banner, selectors, prompts)
├── phases/
│   ├── __init__.py         # Base Phase class (abstract)
│   ├── system.py           # System updates, essentials, GPU drivers
│   ├── shell.py            # zsh, Oh My Zsh, Starship, plugins
│   ├── dev.py              # Node, Python, Docker, Git, editors, languages
│   ├── gaming.py           # Steam, Proton, Gamemode, MangoHud
│   ├── apps.py             # Flatpak apps, Nerd Fonts, peripherals
│   ├── qol.py              # Firewall, SSD trim, swappiness, i2c
│   └── verify.py           # Post-setup verification & health check
├── distros/
│   └── __init__.py         # Distro adapters (Ubuntu apt, Fedora dnf)
└── tests/                  # 60 unit tests
    ├── test_config.py
    ├── test_detector.py
    ├── test_distros.py
    └── test_phases.py
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v                       # Run tests
python -m pytest tests/ --cov=core --cov=phases  # With coverage
ruff check .                                     # Lint
ruff format .                                    # Format
```

### Adding a new phase

1. Create `phases/my_phase.py` inheriting from `Phase`
2. Implement `execute()` with `self.step()` and `self.cmd()` calls
3. Register in `PHASE_REGISTRY` in `distroforge.py`
4. Add tests in `tests/`

### Adding a new distro

1. Add adapter class in `distros/__init__.py` implementing `DistroAdapter`
2. Register in `get_adapter()` factory
3. Add detection in `core/detector.py`

## Design Principles

- **Config-driven** — preferences in YAML, not hardcoded
- **Idempotent** — checks before installing, safe to re-run
- **Logged** — Rich terminal output + file logs in `~/.distroforge/logs/`
- **Dry-run** — preview every command with `--dry-run`
- **Modular** — phases are independent, distro adapters are swappable
- **Tested** — 60 unit tests covering core modules

## Requirements

- Linux (tested on Pop!\_OS 24.04, Ubuntu 24.04)
- Python 3.10+ (`sudo apt install python3` if missing)
- `git` (`sudo apt install git` if missing)
- sudo access

## License

MIT — see [LICENSE](LICENSE)
