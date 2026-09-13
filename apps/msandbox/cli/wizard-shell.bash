# Loaded only for the interactive legacy shell opened by the host-side wizard.
# Exiting with this reserved status hands control back to that already-running
# host process; no Docker socket, tmux socket, or command bridge enters the
# container.
if [[ -f /home/agent/.bashrc ]]; then
    source /home/agent/.bashrc
fi

msandbox() {
    if [[ "$#" -ne 0 ]]; then
        printf '%s\n' 'Use bare `msandbox` to return to the host wizard.' >&2
        return 2
    fi
    exit 86
}

printf '%s\n' 'Type `msandbox` to return to the Matcha Sandbox wizard.'
