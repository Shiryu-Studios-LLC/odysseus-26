#compdef shirabi shirabi-backup shirabi-calendar shirabi-contacts shirabi-cookbook shirabi-docs shirabi-gallery shirabi-mail shirabi-mcp shirabi-memory shirabi-notes shirabi-personal shirabi-preset shirabi-research shirabi-sessions shirabi-signature shirabi-skills shirabi-tasks shirabi-theme shirabi-webhook
# Zsh tab-completion for the shirabi umbrella + sub-CLIs.
#
# Drop in any directory on $fpath, e.g.:
#     fpath=(/path/to/shirabi-ui/scripts/_completion $fpath)
#     autoload -U compinit; compinit
#
# Then `shirabi <tab>` completes subcommands; `shirabi mail <tab>`
# completes mail subcommands; `shirabi-mail <tab>` works the same.

_shirabi_scripts_dir() {
    local self="${(%):-%x}"
    while [[ -L "$self" ]]; do self="$(readlink "$self")"; done
    cd "${self:h}/.." && pwd
}

typeset -gA _shirabi_subs

_shirabi_refresh() {
    _shirabi_subs=()
    local dir="$(_shirabi_scripts_dir)"
    local py="$dir/../venv/bin/python"
    [[ -x "$py" ]] || py="$(command -v python3)"
    local f sub help_out commands
    for f in "$dir"/shirabi-*; do
        [[ -x "$f" ]] || continue
        case "$f" in
            *.bak|*.pyc|*.pre-*) continue ;;
        esac
        sub="${${f:t}#shirabi-}"
        help_out=$("$py" "$f" --help 2>/dev/null) || continue
        commands=$(echo "$help_out" | grep -oE '\{[a-z0-9_,-]+\}' | head -1 \
            | tr -d '{}' | tr ',' ' ')
        _shirabi_subs[$sub]="$commands"
    done
}

_shirabi() {
    [[ ${#_shirabi_subs} -eq 0 ]] && _shirabi_refresh

    local cmd="${words[1]}"

    if [[ "$cmd" == "shirabi" ]]; then
        if (( CURRENT == 2 )); then
            local -a subs=(${(k)_shirabi_subs} help)
            _describe 'subcommand' subs
            return
        fi
        local sub="${words[2]}"
        if [[ "$sub" == "help" ]] && (( CURRENT == 3 )); then
            local -a subs=(${(k)_shirabi_subs})
            _describe 'subcommand' subs
            return
        fi
        if (( CURRENT == 3 )); then
            local -a sc=(${(s/ /)_shirabi_subs[$sub]})
            _describe 'command' sc
            return
        fi
        return
    fi

    # shirabi-foo <tab>
    local sub="${cmd#shirabi-}"
    if (( CURRENT == 2 )); then
        local -a sc=(${(s/ /)_shirabi_subs[$sub]})
        _describe 'command' sc
        return
    fi
}

_shirabi "$@"
