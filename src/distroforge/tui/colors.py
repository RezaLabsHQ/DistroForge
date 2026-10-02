"""Resolved theme colours for Rich ``Text`` styling.

Raw ``Theme`` fields may be ``None`` (Textual derives them), so always read the
resolved ``theme_variables`` instead.
"""

from __future__ import annotations

from textual.app import App


def colour(app: App[object], name: str) -> str:
    variables = app.theme_variables
    return variables.get(name) or variables.get("primary") or "default"
