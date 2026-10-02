## What does this change?

## Checklist

- [ ] `ruff check . && ruff format --check . && mypy` pass
- [ ] `pytest` passes (and new behaviour has tests)
- [ ] Catalog changes: package names verified on each distro listed
- [ ] No `shell=True` / string commands; external values go through `core.validate`
