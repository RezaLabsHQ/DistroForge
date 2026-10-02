from pathlib import Path

import pytest

from distroforge.catalog import Catalog
from distroforge.core.settings import Settings, load_settings, save_settings
from distroforge.core.validate import ValidationError
from distroforge.engine.profiles import (
    builtin_profiles,
    delete_profile,
    load_profile_file,
    load_profiles,
    parse_profile,
    save_profile,
    slugify,
)


def test_builtin_profiles_reference_only_known_items(catalog: Catalog) -> None:
    profiles = builtin_profiles()
    assert {p.id for p in profiles} >= {
        "essentials",
        "developer",
        "gaming",
        "creator",
        "hardening",
        "classic",
    }
    for profile in profiles:
        _, unknown = profile.selection(catalog)
        assert unknown == [], (profile.id, unknown)
        assert profile.builtin


def test_save_load_roundtrip(tmp_path: Path, catalog: Catalog) -> None:
    path = save_profile(tmp_path, "My Laptop!", {"git": None, "vlc": "flatpak"}, description="work")
    assert path.name == "my-laptop.yaml"
    profile = load_profile_file(path)
    assert profile.items == ("git", "vlc")
    assert profile.methods == {"vlc": "flatpak"}
    selection, unknown = profile.selection(catalog)
    assert selection == {"git": None, "vlc": "flatpak"} and unknown == []
    assert [p.id for p in load_profiles(tmp_path) if not p.builtin] == ["my-laptop"]
    delete_profile(profile)
    assert not path.exists()


def test_builtin_profiles_cannot_be_deleted() -> None:
    with pytest.raises(ValueError):
        delete_profile(builtin_profiles()[0])


@pytest.mark.parametrize(
    "data",
    [
        {"items": ["ok", "Bad Id"]},
        {"items": "git"},
        {"items": ["git"], "methods": {"git": "snap"}},
        ["not", "a", "mapping"],
    ],
)
def test_invalid_profiles_rejected(data: object) -> None:
    with pytest.raises(ValidationError):
        parse_profile(data, fallback_id="x", path=None)


def test_broken_user_profile_skipped(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("items: [unclosed")
    assert all(p.builtin for p in load_profiles(tmp_path))


def test_slugify() -> None:
    assert slugify("  Hello World / 2  ") == "hello-world-2"
    assert slugify("!!!") == "profile"


def test_settings_roundtrip_and_permissions(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    save_settings(path, Settings(theme="nord", git_name="Ada", git_email="ada@example.com"))
    assert path.stat().st_mode & 0o777 == 0o600
    loaded = load_settings(path)
    assert loaded.theme == "nord" and loaded.git_email == "ada@example.com"


def test_invalid_settings_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "theme: 'x; rm'\nprefer: snap\ngit_email: nope\ngit_name: '--evil'\nunknown: 1\nskip_installed: yes-ish\n"
    )
    loaded = load_settings(path)
    assert loaded == Settings()


def test_missing_or_garbage_settings(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "none.yaml") == Settings()
    garbage = tmp_path / "g.yaml"
    garbage.write_text("- a list")
    assert load_settings(garbage) == Settings()
