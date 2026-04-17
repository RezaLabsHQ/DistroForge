# DistroForge

**A professional terminal-based Linux distro setup automation tool.**

DistroForge automates the complete setup of a fresh Linux installation — from system updates and driver verification to dev environment, gaming layer, and quality-of-life configuration. One command, fully configured machine.

Built by Hamid at [Reza Labs HQ](https://github.com/rezalabshq)

## Supported Distros

- [x] Ubuntu-based (Ubuntu, Pop!\_OS, Linux Mint, Elementary OS, Zorin)
- [x] Fedora-based (Fedora, Nobara) — _adapter ready, testing in progress_
- [ ] Arch-based (Arch, Manjaro, EndeavourOS) — _planned_

## Quick Start

```bash
git clone https://github.com/rezalabshq/DistroForge.git
cd DistroForge
pip install -r requirements.txt
python3 distroforge.py
```

## Usage

```bash
python3 distroforge.py                            # Interactive mode
python3 distroforge.py --phases system,shell,dev  # Specific phases
python3 distroforge.py --dry-run                  # Preview without executing
python3 distroforge.py --verbose                  # Show full command output
python3 distroforge.py --yes                      # Skip confirmations
python3 distroforge.py --config my-setup.yaml     # Custom config
python3 distroforge.py --distro fedora            # Override detection
python3 distroforge.py --list                     # List phases
python3 distroforge.py --phases verify            # Health check only
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
└── tests/                  # 69 unit tests
    ├── test_config.py
    ├── test_detector.py
    ├── test_distros.py
    └── test_runner.py
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
- **Tested** — 69 unit tests covering core modules

## Requirements

- Python 3.10+
- Linux (tested on Pop!\_OS 24.04, Ubuntu 24.04)
- sudo access

## License

MIT — see [LICENSE](LICENSE)
