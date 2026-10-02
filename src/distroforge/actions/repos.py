"""Repository actions: third-party apt/dnf repos, RPM Fusion, Flathub, Arch multilib."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from distroforge.actions.base import Action, ActionContext, Params, boolean, str_list
from distroforge.core.executor import Command, Result, probe
from distroforge.core.system import Family, SystemInfo
from distroforge.core.validate import check, check_https_url, check_text
from distroforge.engine.ops import CommandOp, Operation, RunContext, TaskOp, install_root_file

APT_KEYRINGS = "/etc/apt/keyrings"
APT_SOURCES = "/etc/apt/sources.list.d"
YUM_REPOS = "/etc/yum.repos.d"


class AptRepo(Action):
    """Add a signed third-party apt repository (key in /etc/apt/keyrings, ``signed-by``)."""

    name = "apt_repo"
    title = "Add APT repository"
    families = frozenset({Family.DEBIAN})
    params: ClassVar = {
        "name": (True, lambda v: check("repo_name", v)),
        "key_url": (True, check_https_url),
        "keyring": (True, lambda v: check("keyring", v)),
        "url": (True, check_https_url),
        "suite": (True, lambda v: check("apt_token", v)),
        "components": (True, str_list(lambda v: check("apt_token", v))),
        "arch": (False, lambda v: check("apt_token", v)),
    }

    def _paths(self, params: Params) -> tuple[str, str]:
        return (
            f"{APT_KEYRINGS}/{params['keyring']}",
            f"{APT_SOURCES}/distroforge-{params['name']}.list",
        )

    def describe(self, params: Params) -> str:
        return f"Add APT repository '{params['name']}' ({params['url']})"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return all(Path(p).exists() for p in self._paths(params))

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        keyring, sources = self._paths(params)
        arch = params.get("arch") or ctx.system.deb_arch
        line = f"deb [arch={arch} signed-by={keyring}] {params['url']} {params['suite']} " + " ".join(
            params["components"]
        )
        return [
            install_root_file(f"Install signing key for {params['name']}", keyring, url=params["key_url"]),
            install_root_file(f"Add {params['name']} repository", sources, content=line + "\n"),
            CommandOp("Refresh APT package lists", Command(("apt-get", "update"), root=True)),
        ]


class DnfRepo(Action):
    name = "dnf_repo"
    title = "Add DNF repository"
    families = frozenset({Family.FEDORA})
    params: ClassVar = {
        "name": (True, lambda v: check("repo_name", v)),
        "title": (True, lambda v: check_text(v, max_len=80, field="repo title")),
        "baseurl": (True, lambda v: check_https_url(v, allow_vars=True)),
        "gpgkey": (True, check_https_url),
    }

    def _path(self, params: Params) -> str:
        return f"{YUM_REPOS}/distroforge-{params['name']}.repo"

    def describe(self, params: Params) -> str:
        return f"Add DNF repository '{params['name']}' ({params['baseurl']})"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return Path(self._path(params)).exists()

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        content = "\n".join(
            [
                f"[{params['name']}]",
                f"name={params['title']}",
                f"baseurl={params['baseurl']}",
                "enabled=1",
                "gpgcheck=1",
                "repo_gpgcheck=0",
                f"gpgkey={params['gpgkey']}",
                "",
            ]
        )
        return [install_root_file(f"Add {params['name']} repository", self._path(params), content=content)]


_FEDORA_IDS = frozenset({"fedora", "nobara", "ultramarine", "bazzite"})


class RpmFusion(Action):
    name = "rpmfusion"
    title = "Enable RPM Fusion"
    families = frozenset({Family.FEDORA})
    params: ClassVar = {"nonfree": (False, boolean)}

    def supported(self, system: SystemInfo, params: Params) -> bool:
        # RHEL clones need EPEL-based RPM Fusion; only Fedora proper is handled.
        return super().supported(system, params) and system.os.id in _FEDORA_IDS

    def _packages(self, params: Params) -> list[str]:
        repos = ["free"] + (["nonfree"] if params.get("nonfree", True) else [])
        return [f"rpmfusion-{r}-release" for r in repos]

    def describe(self, params: Params) -> str:
        return "Enable RPM Fusion (" + " + ".join(self._packages(params)) + ")"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return probe(["rpm", "-q", *self._packages(params)])[0] == 0

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        version = check("apt_token", ctx.system.os.version_id or "0")
        urls = [
            f"https://mirrors.rpmfusion.org/{repo}/fedora/rpmfusion-{repo}-release-{version}.noarch.rpm"
            for repo in (["free", "nonfree"] if params.get("nonfree", True) else ["free"])
        ]
        return [
            CommandOp(
                "Enable RPM Fusion repositories",
                Command(("dnf", "install", "-y", *urls), root=True),
                warning="Adds the third-party RPM Fusion repositories.",
            )
        ]


class Flathub(Action):
    name = "flathub"
    title = "Add the Flathub remote"

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        return ctx.backends.flatpak.has_flathub()

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        return [ctx.backends.flatpak.add_flathub_op()]


class ArchMultilib(Action):
    """Steam and Wine need [multilib]. We check rather than edit pacman.conf."""

    name = "arch_multilib"
    title = "Require the [multilib] repository"
    families = frozenset({Family.ARCH})

    def is_applied(self, params: Params, ctx: ActionContext) -> bool:
        _, out = probe(["pacman-conf", "--repo-list"])
        return "multilib" in out.split()

    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]:
        async def verify(_: RunContext) -> Result:
            if self.is_applied(params, ctx):
                return Result.success()
            return Result.failed(
                "The [multilib] repository is disabled. Uncomment the [multilib] section in "
                "/etc/pacman.conf, run 'sudo pacman -Syu', then retry — or pick the Flatpak method."
            )

        return [
            TaskOp("Check that [multilib] is enabled", verify, ["# pacman-conf --repo-list | grep multilib"])
        ]


ACTIONS: tuple[type[Action], ...] = (AptRepo, DnfRepo, RpmFusion, Flathub, ArchMultilib)
