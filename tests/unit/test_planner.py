import pytest

from distroforge.catalog import Catalog
from distroforge.catalog.models import parse_category, parse_item
from distroforge.core.settings import Settings
from distroforge.core.system import Family
from distroforge.engine.planner import Plan, PlanError, Planner


def stages(plan: Plan) -> list[tuple[str, tuple[str, ...]]]:
    return [(s.stage, s.item_ids) for s in plan.steps]


def step_index(plan: Plan, item_id: str, stage: str) -> int:
    return next(i for i, s in enumerate(plan.steps) if item_id in s.item_ids and s.stage == stage)


def test_native_packages_batched_into_one_transaction(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.FEDORA)).build({"git": None, "jq": None, "tree": None})
    installs = [s for s in plan.steps if s.stage == "install"]
    assert len(installs) == 1
    assert set(installs[0].item_ids) == {"git", "jq", "tree"}
    assert installs[0].ops[0].command.argv == ("dnf", "install", "-y", "git", "jq", "tree")  # type: ignore[attr-defined]


def test_apt_refresh_runs_first(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.DEBIAN)).build({"git": None})
    assert plan.steps[0].stage == "prepare"
    assert "apt-get update" in plan.steps[0].ops[0].preview()[0]


def test_system_upgrade_replaces_refresh_and_runs_first(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.DEBIAN)).build({"git": None, "system-upgrade": None})
    assert plan.steps[0].item_ids == ("system-upgrade",)
    assert sum("apt-get update" in line for s in plan.steps for op in s.ops for line in op.preview()) == 1


def test_flatpak_method_pulls_in_flatpak_first(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.FEDORA)
    env.backends.flatpak.ready = lambda: False  # flatpak not installed yet
    plan = Planner(catalog, env).build({"spotify": None})
    ids = [ip.item.id for ip in plan.items]
    assert ids == ["flatpak", "spotify"]
    assert step_index(plan, "flatpak", "post") < step_index(plan, "spotify", "install")


def test_repo_added_before_package_install(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.DEBIAN)).build({"docker": None})
    pre, install, post = (step_index(plan, "docker", s) for s in ("pre", "install", "post"))
    assert pre < install < post


def test_dependencies_finish_before_dependents(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.FEDORA)).build({"zsh-default": None})
    assert step_index(plan, "zsh", "install") < step_index(plan, "zsh-default", "post")


def test_already_installed_items_are_skipped(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.FEDORA, installed={"git", "jq"})
    plan = Planner(catalog, env).build({"git": None, "jq": None, "tree": None})
    assert {i.id for i, _ in plan.skipped} == {"git", "jq"}
    assert [ip.item.id for ip in plan.items] == ["tree"]
    assert Planner(catalog, env).build({"git": None}, reinstall=True).items


def test_partially_installed_item_only_runs_missing_parts(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(
        Family.FEDORA,
        installed={
            "podman",
            "docker-ce",
            "docker-ce-cli",
            "containerd.io",
            "docker-buildx-plugin",
            "docker-compose-plugin",
        },
        applied={"dnf_repo"},
    )
    plan = Planner(catalog, env).build({"docker": None})
    assert [s.stage for s in plan.steps] == ["post", "post"]  # only service + group remain


def test_unsupported_items_reported_and_dependents_blocked(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.DEBIAN)).build({"rpmfusion": None, "ghostty": None})
    reasons = dict((i.id, r) for i, r in plan.unsupported)
    assert set(reasons) == {"rpmfusion", "ghostty"}
    assert "pacman" in reasons["ghostty"]
    assert plan.empty


def test_method_override_and_preference(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.FEDORA)
    auto = Planner(catalog, env).build({"vlc": None})
    assert [ip.method.backend for ip in auto.items if ip.item.id == "vlc"] == ["dnf"]  # type: ignore[union-attr]
    forced = Planner(catalog, env).build({"vlc": "flatpak"})
    assert [ip.method.backend for ip in forced.items if ip.item.id == "vlc"] == ["flatpak"]  # type: ignore[union-attr]
    flatpak_first = make_env(Family.FEDORA, settings=Settings(prefer="flatpak"))
    pref = Planner(catalog, flatpak_first).build({"vlc": None})
    assert [ip.method.backend for ip in pref.items if ip.item.id == "vlc"] == ["flatpak"]  # type: ignore[union-attr]


def test_script_is_last_resort_and_flagged(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    arch = Planner(catalog, make_env(Family.ARCH)).build({"starship": None})
    assert [ip.method.backend for ip in arch.items if ip.item.id == "starship"] == ["pacman"]  # type: ignore[union-attr]
    fedora = Planner(catalog, make_env(Family.FEDORA)).build({"starship": None})
    assert any("remote script" in w for w in fedora.warnings)


def test_distro_specific_method_selected(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    from distroforge.core.system import OsRelease

    rocky = make_env(Family.FEDORA, os=OsRelease(id="rocky", id_like=("rhel", "centos", "fedora")))
    plan = Planner(catalog, rocky).build({"docker": None})
    text = "\n".join(line for s in plan.steps for op in s.ops for line in op.preview())
    assert "linux/centos" in text and "linux/fedora" not in text


def _mini_catalog(items: list[dict]) -> Catalog:  # type: ignore[type-arg]
    cats = {"system": parse_category({"id": "system", "name": "System"})}
    parsed = {raw["id"]: parse_item(raw, source="t", categories=cats) for raw in items}
    return Catalog(items=parsed, categories=cats)


def test_cycle_detected(make_env) -> None:  # type: ignore[no-untyped-def]
    catalog = _mini_catalog(
        [
            {"id": "a", "name": "A", "category": "system", "requires": ["b"], "install": [{"dnf": "a"}]},
            {"id": "b", "name": "B", "category": "system", "requires": ["a"], "install": [{"dnf": "b"}]},
        ]
    )
    with pytest.raises(PlanError, match="cycle"):
        Planner(catalog, make_env(Family.FEDORA)).build({"a": None})


def test_unknown_item(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PlanError):
        Planner(catalog, make_env(Family.FEDORA)).build({"nope": None})


def test_dependents_of(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.FEDORA)
    env.backends.flatpak.ready = lambda: False
    plan = Planner(catalog, env).build({"spotify": None, "discord": None})
    assert plan.dependents_of("flatpak") == {"spotify", "discord"}


def test_installed_item_does_not_pull_in_dependencies(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.FEDORA, installed={"com.spotify.Client"})
    plan = Planner(catalog, env).build({"spotify": "flatpak"})
    assert [i.id for i, _ in plan.skipped] == ["spotify"]
    assert plan.items == [] and plan.empty


def test_unsupported_item_does_not_pull_in_dependencies(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.DEBIAN)).build({"ghostty": None})
    assert [i.id for i, _ in plan.unsupported] == ["ghostty"]
    assert plan.items == []


def test_existing_flatpak_used_without_bootstrap(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.FEDORA)).build({"spotify": None})
    assert [ip.item.id for ip in plan.items] == ["spotify"]
    previews = [line for s in plan.steps for op in s.ops for line in op.preview()]
    assert any("remote-add --user --if-not-exists flathub" in p for p in previews)


def test_unknown_family_with_flatpak_installs_flatpaks(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.UNKNOWN)).build({"vlc": None, "git": None})
    assert [ip.item.id for ip in plan.items] == ["vlc"]
    assert [i.id for i, _ in plan.unsupported] == ["git"]


def test_unknown_family_without_flatpak_reports_unsupported(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.UNKNOWN)
    env.backends.flatpak.ready = lambda: False
    plan = Planner(catalog, env).build({"vlc": None})
    assert plan.items == [] and [i.id for i, _ in plan.unsupported] == ["vlc"]


def test_aur_plans_require_sudo_credentials(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    env = make_env(Family.ARCH, aur_helper="paru")
    plan = Planner(catalog, env).build({"vscodium": "aur"})
    assert plan.needs_root  # paru calls sudo internally; credentials must be validated first


def test_third_party_repositories_are_flagged(catalog: Catalog, make_env) -> None:  # type: ignore[no-untyped-def]
    plan = Planner(catalog, make_env(Family.DEBIAN)).build({"docker": None})
    assert any("third-party package repository from download.docker.com" in w for w in plan.warnings)
    fedora = Planner(catalog, make_env(Family.FEDORA)).build({"vscode": None})
    assert any("packages.microsoft.com" in w for w in fedora.warnings)
