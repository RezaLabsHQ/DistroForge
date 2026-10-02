"""Action framework.

An action is a named, parameterised, idempotent setup step that catalog files
can reference, e.g. ``{action: service, unit: docker.service}``. Each action:

* validates its parameters (strictly, at catalog load *and* at plan time),
* reports whether it is already applied (``True``/``False``/``None`` = unknown),
* produces the operations that apply it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from distroforge.backends import Backends
from distroforge.core.settings import Settings
from distroforge.core.system import Family, SystemInfo
from distroforge.core.validate import ValidationError
from distroforge.engine.ops import Operation


@dataclass(frozen=True)
class ActionContext:
    system: SystemInfo
    backends: Backends
    settings: Settings


Params = dict[str, Any]


class Action(ABC):
    name: ClassVar[str]
    title: ClassVar[str]
    #: Families this action works on; ``None`` means all.
    families: ClassVar[frozenset[Family] | None] = None
    #: Early actions (e.g. a full upgrade) run before any other step in a plan.
    early: ClassVar[bool] = False
    #: param name → (required, validator). Validators return the cleaned value.
    params: ClassVar[Mapping[str, tuple[bool, Callable[[Any], Any]]]] = {}

    def parse(self, raw: Mapping[str, Any]) -> Params:
        unknown = set(raw) - set(self.params)
        if unknown:
            raise ValidationError(f"{self.name}: unknown parameter(s) {sorted(unknown)}")
        out: Params = {}
        for key, (required, validator) in self.params.items():
            if key not in raw:
                if required:
                    raise ValidationError(f"{self.name}: missing parameter '{key}'")
                continue
            out[key] = validator(raw[key])
        return out

    def supported(self, system: SystemInfo, params: Params) -> bool:
        return self.families is None or system.family in self.families

    def describe(self, params: Params) -> str:
        return self.title

    @abstractmethod
    def is_applied(self, params: Params, ctx: ActionContext) -> bool | None: ...

    @abstractmethod
    def ops(self, params: Params, ctx: ActionContext) -> list[Operation]: ...


# ── validators reused by actions ──


def str_list(validator: Callable[[Any], str]) -> Callable[[Any], list[str]]:
    def inner(value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not value:
            raise ValidationError(f"Expected a non-empty list, got {value!r}")
        return [validator(v) for v in value]

    return inner


def boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"Expected true/false, got {value!r}")
    return value
