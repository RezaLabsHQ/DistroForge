import ast
from pathlib import Path

import pytest

import distroforge
from distroforge.core.executor import Command, Executor, Status, probe


def test_root_command_uses_non_interactive_sudo() -> None:
    cmd = Command(("apt-get", "install", "-y", "git"), root=True, env={"DEBIAN_FRONTEND": "noninteractive"})
    assert cmd.full_argv() == [
        "sudo", "-n", "--", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "git",
    ]
    assert cmd.display() == "sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y git"


def test_display_quotes_arguments() -> None:
    assert Command(("echo", "a b", "$HOME")).display() == "echo 'a b' '$HOME'"


@pytest.mark.parametrize("argv", [(), ("",), ("echo", "\0")])
def test_invalid_argv_rejected(argv: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        Command(argv)


async def test_streams_output_and_succeeds() -> None:
    lines: list[str] = []
    result = await Executor().run(Command(("printf", "one\\ntwo\\rthree\\n")), lines.append)
    assert result.status is Status.SUCCESS
    assert lines == ["one", "two", "three"]


async def test_shell_metacharacters_are_not_interpreted(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    lines: list[str] = []
    result = await Executor().run(Command(("echo", f"; touch {marker}")), lines.append)
    assert result.status is Status.SUCCESS
    assert lines == [f"; touch {marker}"]
    assert not marker.exists()


async def test_failure_reports_exit_code_and_tail() -> None:
    result = await Executor().run(Command(("sh", "-c", "echo boom; exit 3")))
    assert result.status is Status.FAILED
    assert result.returncode == 3
    assert "boom" in result.output_tail


async def test_ok_codes() -> None:
    result = await Executor().run(Command(("sh", "-c", "exit 100"), ok_codes=frozenset({0, 100})))
    assert result.status is Status.SUCCESS


async def test_timeout_kills_process() -> None:
    result = await Executor().run(Command(("sleep", "30"), timeout=0.3))
    assert result.status is Status.FAILED
    assert "Timed out" in result.message


async def test_missing_binary() -> None:
    result = await Executor().run(Command(("definitely-not-a-real-binary-xyz",)))
    assert result.status is Status.FAILED
    assert result.returncode == 127


async def test_env_passed_to_non_root_command() -> None:
    lines: list[str] = []
    await Executor().run(Command(("sh", "-c", "echo $DF_TEST"), env={"DF_TEST": "ok"}), lines.append)
    assert lines == ["ok"]


def test_probe() -> None:
    assert probe(["sh", "-c", "echo hi"]) == (0, "hi\n")
    assert probe(["definitely-not-a-real-binary-xyz"])[0] == 127


def test_no_shell_true_anywhere() -> None:
    """Security invariant: no module may call subprocess with shell=True."""
    root = Path(distroforge.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        offenders.append(f"{path}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in {"system", "popen"}:
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    offenders.append(f"{path}:{node.lineno}")
    assert offenders == []
