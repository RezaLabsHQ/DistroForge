# bash completion for distroforge
_distroforge_reply() { mapfile -t COMPREPLY < <(compgen "$@"); }

_distroforge() {
    local cur="${COMP_WORDS[COMP_CWORD]}" prev="${COMP_WORDS[COMP_CWORD-1]}"
    local commands="tui list apply profiles doctor validate integrate"
    local sub="" i
    for ((i = 1; i < COMP_CWORD; i++)); do
        case "${COMP_WORDS[i]}" in tui|list|apply|profiles|doctor|validate|integrate) sub="${COMP_WORDS[i]}"; break ;; esac
    done
    case "$prev" in
        --distro) _distroforge_reply -W "debian fedora arch" -- "$cur"; return ;;
        --profile|-p) _distroforge_reply -W "$(distroforge profiles 2>/dev/null | awk '/^[a-z]/ {print $1}')" -- "$cur"; return ;;
        --category) _distroforge_reply -W "system shell development languages editors browsers communication media graphics productivity gaming utilities virtualization fonts peripherals tweaks" -- "$cur"; return ;;
    esac
    case "$sub" in
        "") _distroforge_reply -W "$commands --distro --version --help" -- "$cur" ;;
        tui) _distroforge_reply -W "--dry-run" -- "$cur" ;;
        list) _distroforge_reply -W "--category --installed" -- "$cur" ;;
        apply)
            if [[ "$cur" == -* ]]; then
                _distroforge_reply -W "--profile --method --dry-run --yes --reinstall --fail-fast --verbose" -- "$cur"
            else
                _distroforge_reply -W "$(distroforge list --ids 2>/dev/null)" -- "$cur"
            fi ;;
        validate) _distroforge_reply -f -X '!*.@(yaml|yml)' -- "$cur" ;;
        integrate) _distroforge_reply -W "--remove" -- "$cur" ;;
    esac
}
complete -F _distroforge distroforge
