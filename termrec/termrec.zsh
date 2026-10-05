# termrec zsh integration
# Provides the user-facing `rec` command and semantic command/output markers while a
# recording shell is active.

function _termrec_preexec() {
    [[ -n "${TERMREC_ACTIVE:-}" ]] || return 0

    # $1 is the command line exactly as zsh accepted it. The exporter uses this marker
    # instead of trying to recover commands from a decorated Powerlevel10k prompt.
    if [[ -n "${TERMREC_PYTHON:-}" ]]; then
        command "$TERMREC_PYTHON" -m termrec.cli _command-start "$1" --cwd "$PWD"
    else
        command termrec _command-start "$1" --cwd "$PWD"
    fi
}

function _termrec_precmd() {
    local command_status=$?
    [[ -n "${TERMREC_ACTIVE:-}" ]] || return 0

    # This marker closes the output range of the previous command before the next prompt
    # is rendered, so prompt/theme output is never part of the exported transcript.
    if [[ -n "${TERMREC_PYTHON:-}" ]]; then
        command "$TERMREC_PYTHON" -m termrec.cli _command-end "$command_status"
    else
        command termrec _command-end "$command_status"
    fi
}

function _termrec_enable_hooks() {
    [[ -n "${TERMREC_ACTIVE:-}" ]] || return 0

    autoload -Uz add-zsh-hook

    # Avoid duplicates if .zshrc is sourced again during a recording.
    add-zsh-hook -d preexec _termrec_preexec 2>/dev/null || true
    add-zsh-hook -d precmd _termrec_precmd 2>/dev/null || true

    add-zsh-hook preexec _termrec_preexec
    add-zsh-hook precmd _termrec_precmd
}

function rec() {
    if [[ "${1:-}" == stop ]]; then
        if [[ -n "${TERMREC_PYTHON:-}" ]]; then
            command "$TERMREC_PYTHON" -m termrec.cli _stop-marker
        else
            command termrec _stop-marker
        fi
        exit
    fi
    if [[ -n "${TERMREC_PYTHON:-}" ]]; then
        command "$TERMREC_PYTHON" -m termrec.cli "$@"
    else
        command termrec "$@"
    fi
}

_termrec_enable_hooks
