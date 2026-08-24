#!/usr/bin/env bash
set -euo pipefail

template_version="$(cat /opt/bootstrap/.dependencies-sha)"

sync_dependency_tree() {
    local source_dir=$1
    local destination_dir=$2
    local installed_version=""

    if [[ -f "${destination_dir}/.codex-sandbox-template" ]]; then
        installed_version="$(cat "${destination_dir}/.codex-sandbox-template")"
    fi

    if [[ "$installed_version" != "$template_version" ]]; then
        mkdir -p "$destination_dir"
        rsync -a --delete "${source_dir}/" "${destination_dir}/"
        printf '%s\n' "$template_version" > "${destination_dir}/.codex-sandbox-template"
        chown -R codex:codex "$destination_dir"
    fi
}

sync_dependency_tree /opt/bootstrap/server-venv /workspace/server/venv
sync_dependency_tree /opt/bootstrap/client-node_modules /workspace/client/node_modules
sync_dependency_tree /opt/bootstrap/tellus-node_modules /workspace/client/tellus/node_modules
sync_dependency_tree /opt/bootstrap/oceanlab-node_modules /workspace/client/oceanlab/node_modules

# Python virtualenv activation scripts contain their original build location.
# Rewrite text files after the copy so commands use the named-volume venv.
for executable in /workspace/server/venv/bin/*; do
    if [[ -f "$executable" ]] && grep -Iq . "$executable"; then
        sed -i 's|/opt/bootstrap/server-venv|/workspace/server/venv|g' "$executable"
    fi
done

install -d -o codex -g codex \
    /home/codex \
    /home/codex/.codex \
    /home/codex/.config/gh \
    /home/codex/.config/git \
    /home/codex/.cache \
    /home/codex/.npm

exec gosu codex "$@"
