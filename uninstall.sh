#!/usr/bin/env bash
# DistroForge uninstaller — removes the app, menu entry, icon and completions.
# Your settings and profiles in ~/.config/distroforge are kept unless you pass --purge.
# Software that DistroForge installed for you is NOT removed.
set -euo pipefail

APP="distroforge"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
APP_DIR="$DATA_HOME/$APP"
BIN="$HOME/.local/bin/$APP"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

if [[ -t 1 ]]; then G=$'\033[32m' N=$'\033[0m'; else G="" N=""; fi
ok() { printf ' %s✓%s %s\n' "$G" "$N" "$*"; }

if command -v "$APP" >/dev/null 2>&1; then
    if "$APP" integrate --remove >/dev/null 2>&1; then
        ok "Removed menu entry, icon and completions"
    fi
fi

METHOD="$(cat "$APP_DIR/install-method" 2>/dev/null || echo venv)"
if [[ "$METHOD" == "pipx" ]] && command -v pipx >/dev/null 2>&1; then
    if pipx uninstall "$APP" >/dev/null 2>&1; then
        ok "Removed pipx package"
    fi
fi
if [[ -L "$BIN" ]] || { [[ -f "$BIN" ]] && grep -q "distroforge" "$BIN" 2>/dev/null; }; then
    rm -f -- "$BIN" && ok "Removed $BIN"
fi
if [[ -d "$APP_DIR" ]]; then
    rm -rf -- "${APP_DIR:?}" && ok "Removed $APP_DIR"
fi
if [[ "$PURGE" == 1 ]]; then
    rm -rf -- "${CONFIG_HOME:?}/$APP" "${STATE_HOME:?}/$APP" && ok "Removed settings, profiles and logs"
else
    printf '   Settings and profiles kept in %s (use --purge to delete)\n' "$CONFIG_HOME/$APP"
fi
printf '\nDistroForge has been uninstalled. Thanks for using it!\n'
