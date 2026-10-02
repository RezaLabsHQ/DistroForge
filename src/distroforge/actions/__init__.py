"""Action registry. Catalog files reference actions by ``name``."""

from __future__ import annotations

from distroforge.actions import repos, system, user
from distroforge.actions.base import Action, ActionContext, Params

REGISTRY: dict[str, Action] = {cls.name: cls() for cls in (*repos.ACTIONS, *system.ACTIONS, *user.ACTIONS)}


def get_action(name: str) -> Action:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown action '{name}'. Available: {', '.join(sorted(REGISTRY))}") from None


__all__ = ["REGISTRY", "Action", "ActionContext", "Params", "get_action"]
