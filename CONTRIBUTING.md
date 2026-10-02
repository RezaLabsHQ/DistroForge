# Contributing to DistroForge

Thanks for helping! Most contributions are catalog entries: adding an app is usually a few lines of YAML.

## Setup

```bash
git clone https://github.com/RezaLabsHQ/DistroForge.git && cd DistroForge
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
distroforge tui --dry-run      # safe: nothing is executed
```

## Checks (CI runs all of these)

```bash
ruff check . && ruff format --check .
mypy                                     # strict
pytest                                   # unit + UI tests
pytest -m integration tests/integration  # real installs in containers (needs podman/docker)
```

## Adding or fixing an app

1. Pick the right file in `src/distroforge/catalog/data/` (one per category group).
2. Add an item. List methods for every family you can verify, plus Flatpak if one exists on Flathub:

   ```yaml
   - id: my-app                 # lowercase, unique
     name: My App
     category: utilities        # see 00-categories.yaml
     description: One line, no trailing period
     install:
       - apt: my-app
       - dnf: my-app
       - pacman: my-app
       - flatpak: org.example.MyApp
   ```

3. **Verify package names** on each distro: [packages.ubuntu.com](https://packages.ubuntu.com), [packages.debian.org](https://packages.debian.org), [packages.fedoraproject.org](https://packages.fedoraproject.org), [archlinux.org/packages](https://archlinux.org/packages), [flathub.org](https://flathub.org).
4. Prefer distro packages and Flatpak. Use `script:` only for tools whose official install method is a script. Scripts need a `check:` and should pin a `sha256` when the upstream script is versioned.
5. Run `pytest tests/unit/test_catalog.py`. It validates the whole catalog and plans every item on every family.

## Code layout

| Path                         | What lives there                                              |
| ---------------------------- | ------------------------------------------------------------- |
| `src/distroforge/core/`      | detection, paths, settings, validation, executor, sudo, shell rc, downloads |
| `src/distroforge/backends/`  | apt, dnf, pacman, AUR, Flatpak (one class each)                |
| `src/distroforge/actions/`   | named, idempotent setup steps referenced from YAML            |
| `src/distroforge/catalog/`   | data model, loader, built-in YAML data and profiles           |
| `src/distroforge/engine/`    | resolver, planner, runner, profiles                           |
| `src/distroforge/tui/`       | Textual app, screens, themes, stylesheet                      |
| `src/distroforge/cli.py`     | command-line entry point                                      |

**Adding a package manager:** subclass `backends.base.Backend`, register it in `backends/__init__.py`, and add the family to `core/system.py`.

**Adding an action:** subclass `actions.base.Action` with strict `params` validators, `is_applied` and `ops`, then register it. Actions must be idempotent and must never build shell strings.

## Rules

- Never use `shell=True`, `os.system` or string commands. Build `Command((...argv...))`. A test enforces this.
- Validate every external value with `core.validate`.
- Root writes go through `engine.ops.install_root_file` (allow-listed directories only).
- Keep the UI responsive: probes and planning run in worker threads.
- Commits: conventional style (`feat:`, `fix:`, `docs:` …).
