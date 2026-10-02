# fish completion for distroforge
set -l commands tui list apply profiles doctor validate integrate
complete -c distroforge -f
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a tui -d "Open the full-screen app"
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a list -d "List catalog items"
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a apply -d "Install items or a profile"
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a profiles -d "List profiles"
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a doctor -d "Check the environment"
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a validate -d "Validate catalog files"
complete -c distroforge -n "not __fish_seen_subcommand_from $commands" -a integrate -d "Menu entry, icon and completions"
complete -c distroforge -l version -d "Show version"
complete -c distroforge -l distro -xa "debian fedora arch" -d "Override family detection"
complete -c distroforge -n "__fish_seen_subcommand_from tui" -l dry-run
complete -c distroforge -n "__fish_seen_subcommand_from list" -l category -x
complete -c distroforge -n "__fish_seen_subcommand_from list" -l installed
complete -c distroforge -n "__fish_seen_subcommand_from apply" -a "(distroforge list --ids 2>/dev/null)"
complete -c distroforge -n "__fish_seen_subcommand_from apply" -s p -l profile -xa "(distroforge profiles 2>/dev/null | awk '/^[a-z]/ {print \$1}')"
complete -c distroforge -n "__fish_seen_subcommand_from apply" -s m -l method -x
complete -c distroforge -n "__fish_seen_subcommand_from apply" -s n -l dry-run
complete -c distroforge -n "__fish_seen_subcommand_from apply" -s y -l yes
complete -c distroforge -n "__fish_seen_subcommand_from apply" -l reinstall
complete -c distroforge -n "__fish_seen_subcommand_from apply" -l fail-fast
complete -c distroforge -n "__fish_seen_subcommand_from apply" -s v -l verbose
complete -c distroforge -n "__fish_seen_subcommand_from validate" -F
complete -c distroforge -n "__fish_seen_subcommand_from integrate" -l remove
