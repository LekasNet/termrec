# termrec bash integration, loaded only inside a recording shell.

_termrec_command() {
    "$TERMREC_PYTHON" -m termrec.cli "$@"
}

_termrec_preexec() {
    [[ -n ${TERMREC_ACTIVE:-} ]] || return
    [[ ${BASH_COMMAND:-} == _termrec_* ]] && return
    _termrec_command _command-start "$BASH_COMMAND" --cwd "$PWD"
}

_termrec_precmd() {
    local status=$?
    [[ -n ${TERMREC_ACTIVE:-} ]] || return
    _termrec_command _command-end "$status"
}

# Set the prompt handler before DEBUG is enabled, so setup itself is not exported.
# DEBUG runs immediately before a simple command; PROMPT_COMMAND closes its output.
PROMPT_COMMAND='_termrec_precmd'
trap '_termrec_preexec' DEBUG

rec() {
    if [[ ${1:-} == stop ]]; then
        _termrec_command _stop-marker
        exit
    fi
    _termrec_command "$@"
}
