# Contributing to DistroForge

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/rezalabshq/DistroForge.git
cd DistroForge
pip install -r requirements-dev.txt
```

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=core --cov=phases --cov=distros

# Single test file
python -m pytest tests/test_detector.py -v
```

## Code Quality

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy core/ phases/ distros/ --ignore-missing-imports
```

## Project Structure

- `core/` — Framework internals (detection, execution, logging, UI)
- `phases/` — Setup phases (each phase is one file, one class)
- `distros/` — Package manager adapters (one class per distro family)
- `tests/` — Unit tests mirroring the source structure

## Adding a Phase

1. Create `phases/your_phase.py`
2. Inherit from `Phase`, implement `execute()`
3. Use `self.step()` for progress, `self.cmd()` for commands
4. Register in `PHASE_REGISTRY` in `distroforge.py`
5. Add tests in `tests/test_your_phase.py`

## Adding a Distro

1. Create adapter class in `distros/__init__.py`
2. Implement all `DistroAdapter` abstract methods
3. Add to `get_adapter()` factory
4. Add detection logic in `core/detector.py`
5. Add tests in `tests/test_distros.py`

## Pull Request Guidelines

- One feature per PR
- Tests must pass (`python -m pytest tests/ -v`)
- Lint must pass (`ruff check .`)
- Write clear commit messages
- Update README if adding user-facing features

## Commit Messages

Use conventional commits:

```
feat: add Arch Linux adapter
fix: handle missing /etc/os-release gracefully
docs: update README with new phase
test: add GPU detection edge cases
refactor: extract SSH key setup into helper method
```
