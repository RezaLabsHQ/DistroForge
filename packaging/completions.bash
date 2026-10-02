#!/usr/bin/env bash
# DistroForge — Shell Completions
# Source this file in your .bashrc or .zshrc:
#   source /path/to/completions.sh

_distroforge_phases="system shell dev gaming apps qol verify"

_distroforge_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Top-level options
    opts="--phases --dry-run --verbose --yes --config --list --distro --version --help"

    case "${prev}" in
        --phases)
            # Complete phase names (comma-separated)
            local phases="${_distroforge_phases}"
            # Handle comma-separated completion
            local prefix=""
            if [[ "$cur" == *,* ]]; then
                prefix="${cur%,*},"
                cur="${cur##*,}"
            fi
            local completions=""
            for phase in $phases; do
                completions="$completions ${prefix}${phase}"
            done
            COMPREPLY=( $(compgen -W "$completions" -- "$cur") )
            # Don't add trailing space after comma-separated values
            compopt -o nospace 2>/dev/null
            return 0
            ;;
        --config|-c)
            # Complete file paths (yaml files)
            COMPREPLY=( $(compgen -f -X '!*.y*ml' -- "$cur") )
            return 0
            ;;
        --distro)
            COMPREPLY=( $(compgen -W "ubuntu fedora" -- "$cur") )
            return 0
            ;;
    esac

    COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
    return 0
}

# Register for bash
if [ -n "$BASH_VERSION" ]; then
    complete -F _distroforge_completions distroforge
    complete -F _distroforge_completions distroforge.py
    complete -F _distroforge_completions "python3 distroforge.py"
fi

# Register for zsh (if using bashcompinit)
if [ -n "$ZSH_VERSION" ]; then
    autoload -U bashcompinit && bashcompinit
    complete -F _distroforge_completions distroforge
    complete -F _distroforge_completions distroforge.py
fi