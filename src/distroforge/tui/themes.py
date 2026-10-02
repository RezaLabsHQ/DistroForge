"""Themes. Catppuccin (all four flavours) and other popular palettes ship with
Textual; DistroForge adds its own "forge" brand theme and curates the cycle order."""

from __future__ import annotations

from textual.theme import Theme

FORGE = Theme(
    name="forge",
    primary="#FF8A3D",  # molten metal
    secondary="#7AA2F7",
    accent="#F7C948",  # spark
    warning="#E0AF68",
    error="#F7768E",
    success="#9ECE6A",
    foreground="#E6E1DC",
    background="#14161B",
    surface="#1C1F26",
    panel="#262B35",
    dark=True,
)

FORGE_LIGHT = Theme(
    name="forge-light",
    primary="#D9480F",
    secondary="#1C7ED6",
    accent="#E67700",
    warning="#E67700",
    error="#C92A2A",
    success="#2B8A3E",
    foreground="#1F2328",
    background="#FAF7F2",
    surface="#F1ECE4",
    panel="#E6DED2",
    dark=False,
)

CUSTOM_THEMES = (FORGE, FORGE_LIGHT)

#: Order used by the "cycle theme" key and the Settings picker.
THEME_CHOICES: tuple[tuple[str, str], ...] = (
    ("catppuccin-mocha", "Catppuccin Mocha"),
    ("catppuccin-macchiato", "Catppuccin Macchiato"),
    ("catppuccin-frappe", "Catppuccin Frappé"),
    ("catppuccin-latte", "Catppuccin Latte (light)"),
    ("forge", "Forge (DistroForge brand)"),
    ("forge-light", "Forge Light"),
    ("tokyo-night", "Tokyo Night"),
    ("nord", "Nord"),
    ("gruvbox", "Gruvbox"),
    ("dracula", "Dracula"),
    ("rose-pine", "Rosé Pine"),
    ("rose-pine-dawn", "Rosé Pine Dawn (light)"),
    ("solarized-dark", "Solarized Dark"),
    ("textual-dark", "Textual Dark"),
)

THEME_NAMES = tuple(name for name, _ in THEME_CHOICES)


def next_theme(current: str) -> str:
    try:
        return THEME_NAMES[(THEME_NAMES.index(current) + 1) % len(THEME_NAMES)]
    except ValueError:
        return THEME_NAMES[0]
