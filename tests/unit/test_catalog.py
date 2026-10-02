from pathlib import Path

import pytest

from distroforge.catalog import Catalog, load_catalog
from distroforge.catalog.models import parse_item, substitute
from distroforge.core.system import Family
from distroforge.core.validate import ValidationError
from distroforge.engine.planner import Planner
from distroforge.engine.resolve import Resolver

FAMILIES = (Family.DEBIAN, Family.FEDORA, Family.ARCH)


def test_builtin_catalog_has_no_errors(catalog: Catalog) -> None:
    assert catalog.errors == ()
    assert len(catalog.items) >= 120


def test_every_item_category_exists(catalog: Catalog) -> None:
    for item in catalog.items.values():
        assert item.category in catalog.categories, item.id


def test_every_item_installable_on_at_least_one_family(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    envs = [make_env(f) for f in FAMILIES]
    for item in catalog.items.values():
        assert any(Resolver(env).supported(item) for env in envs), item.id


@pytest.mark.parametrize("family", FAMILIES)
def test_broad_coverage_per_family(catalog: Catalog, make_env, family: Family) -> None:  # type: ignore[no-untyped-def]
    resolver = Resolver(make_env(family))
    unsupported = [i.id for i in catalog.items.values() if not resolver.supported(i)]
    # Only genuinely family-specific items may be missing (e.g. RPM Fusion, AUR-only tools).
    assert len(unsupported) <= 6, unsupported


@pytest.mark.parametrize("family", FAMILIES)
def test_whole_catalog_plans_without_errors(catalog: Catalog, make_env, family: Family) -> None:  # type: ignore[no-untyped-def]
    """Selecting *everything* must produce a valid, cycle-free plan on every family."""
    env = make_env(family)
    plan = Planner(catalog, env).build({item_id: None for item_id in catalog.items})
    assert plan.steps
    planned = {ip.item.id for ip in plan.items}
    unsupported = {item.id for item, _ in plan.unsupported}
    assert planned | unsupported == set(catalog.items)
    for step in plan.steps:
        for op in step.ops:
            assert op.preview(), step.title


def test_shell_syntax_survives_substitution() -> None:
    line = '(( ${+functions[omz]} )) || { source "$ZSH/oh-my-zsh.sh"; } {home}'
    assert substitute(line, {"home": "/h"}) == '(( ${+functions[omz]} )) || { source "$ZSH/oh-my-zsh.sh"; } /h'


def _write(directory: Path, name: str, text: str) -> None:
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(text)


def test_user_catalog_adds_overrides_and_hides(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mine.yaml",
        """
categories:
  - { id: work, name: Work stuff }
items:
  - id: my-tool
    name: My Tool
    category: work
    install:
      - flatpak: com.example.MyTool
  - id: git
    name: Git (my override)
    category: system
    install:
      - dnf: git-core
hide: [spotify]
""",
    )
    catalog = load_catalog(tmp_path)
    assert catalog.errors == ()
    assert catalog.items["my-tool"].source == "user: mine.yaml"
    assert catalog.items["git"].name == "Git (my override)"
    assert "spotify" not in catalog.items
    assert "work" in catalog.categories


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("install: [{apt: '; rm -rf /'}]", "Invalid package"),
        ("install: [{flatpak: notanid}]", "Invalid flatpak"),
        ("install: [{script: {url: 'http://x.sh'}}]", "https"),
        ("install: [{script: {url: 'https://x.sh/i'}}]", "need a 'check'"),
        ("install: [{apt: git, dnf: git}]", "exactly one"),
        ("install: [{snap: git}]", "exactly one"),
        ("post: [{action: nope}]", "Unknown action"),
        ("post: [{action: sysctl, key: vm.swappiness, value: '10; reboot'}]", "sysctl value"),
        ("post: [{action: service}]", "missing parameter"),
        ("install: [{apt: git}]\nbogus: 1", "unknown key"),
        ("", "at least one install method"),
    ],
)
def test_invalid_items_are_reported_not_fatal(tmp_path: Path, snippet: str, message: str) -> None:
    body = "\n".join("    " + line for line in snippet.splitlines())
    _write(tmp_path, "bad.yaml", f"items:\n  - id: bad-item\n    name: Bad\n    category: system\n{body}\n")
    catalog = load_catalog(tmp_path)
    assert "bad-item" not in catalog.items
    assert any(message in err for err in catalog.errors), catalog.errors
    assert "git" in catalog.items  # the rest still loads


def test_dangling_requires_dropped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "x.yaml",
        "items:\n  - {id: needs-ghost, name: X, category: system, requires: [ghost], install: [{apt: x}]}\n",
    )
    catalog = load_catalog(tmp_path)
    assert "needs-ghost" not in catalog.items
    assert any("ghost" in e for e in catalog.errors)


def test_broken_yaml_reported(tmp_path: Path) -> None:
    _write(tmp_path, "broken.yaml", "items: [unclosed")
    catalog = load_catalog(tmp_path)
    assert any("invalid YAML" in e for e in catalog.errors)


def test_parse_item_requires_known_category(catalog: Catalog) -> None:
    with pytest.raises(ValidationError):
        parse_item(
            {"id": "x", "name": "X", "category": "nope", "install": [{"apt": "x"}]},
            source="t",
            categories=catalog.categories,
        )
