#!/usr/bin/env bash
# What a PR's CI needs to run, from the files it changed.
#
#   git diff --name-only BASE...HEAD | scripts/ci/select_scope.sh
#   CI_FULL=1 scripts/ci/select_scope.sh </dev/null      # everything
#
# Prints GitHub-output lines (key=value):
#
#   full=true|false          everything runs (push to main, ci:full, a CI edit)
#   server=true|false        any server code changed (Markdown doesn't count)
#   server_scope=all|cappe|tellus|oceanlab|none
#   server_tests=<paths>     what pytest runs from server/ ("tests" = the whole
#                            suite; empty = skip the matcha suite)
#   oceanlab_tests=true|false
#   client=true|false        the main client app (client/, minus the sub-apps)
#   tellus=true|false        client/tellus
#   oceanlab_client=true|false
#   ops=true|false           scripts/, apps/ or server/ (syntax + ops tests)
#
# The scoping leans on the import rule in the root CLAUDE.md: cappe/, tellus/
# and oceanlab/ import only from app/core, never from each other or matcha.
# So a change that stays inside one of them can only break that app's tests
# plus the few shared tests that import it (listed below, found with
# `git grep -l 'app\.cappe' server/tests`). A change that touches anything
# else — app/core, app/matcha, main.py, config, requirements, pytest.ini, a
# conftest — or spans two apps runs the whole suite. It never guesses across
# a boundary. A push to main always runs everything (CI_FULL=1), so anything
# a scoped PR run could miss is caught right after merge.
#
# Changing this file or ci.yml runs everything: a selector bug must not be
# able to wave itself through.
set -euo pipefail

CAPPE_TESTS="tests/cappe tests/workers/test_cappe_*.py tests/core/test_ai_usage.py tests/test_scoped_auth.py tests/alembic"
TELLUS_TESTS="tests/tellus tests/test_scoped_auth.py tests/alembic"

emit_all() {
    cat <<EOF
full=true
server=true
server_scope=all
server_tests=tests
oceanlab_tests=true
client=true
tellus=true
oceanlab_client=true
ops=true
EOF
}

if [ "${CI_FULL:-}" = "1" ]; then
    emit_all
    exit 0
fi

changed="$(grep -v '^[[:space:]]*$' || true)"

if grep -qE '^(\.github/workflows/ci\.yml|scripts/ci/)' <<< "$changed"; then
    emit_all
    exit 0
fi

server_files="$(grep -E '^server/' <<< "$changed" | grep -vE '\.md$' || true)"
server=false
[ -n "$server_files" ] && server=true

scope=none
if [ -n "$server_files" ]; then
    areas=""
    while IFS= read -r f; do
        case "$f" in
            server/app/cappe/*|server/app/workers/tasks/cappe_*|server/tests/cappe/*|server/tests/workers/test_cappe_*)
                area=cappe ;;
            server/alembic/versions/zzzzcappe*|server/alembic/versions/cappe*)
                area=cappe ;;
            server/app/tellus/*|server/tests/tellus/*|server/alembic/versions/tellus*)
                area=tellus ;;
            server/app/oceanlab/*|server/alembic/versions/oceanlab*)
                area=oceanlab ;;
            *)
                area=all ;;
        esac
        areas="$areas $area"
    done <<< "$server_files"
    distinct="$(tr ' ' '\n' <<< "$areas" | grep -v '^$' | sort -u)"
    if [ "$(wc -l <<< "$distinct")" -eq 1 ]; then
        scope="$distinct"
    else
        scope=all
    fi
fi

case "$scope" in
    all) server_tests=tests; oceanlab_tests=true ;;
    cappe) server_tests="$CAPPE_TESTS"; oceanlab_tests=false ;;
    tellus) server_tests="$TELLUS_TESTS"; oceanlab_tests=false ;;
    oceanlab) server_tests="tests/alembic"; oceanlab_tests=true ;;
    *) server_tests=""; oceanlab_tests=false ;;
esac

flag() { grep -qE "$1" <<< "$changed" && echo true || echo false; }

client="$(grep -E '^client/' <<< "$changed" | grep -qvE '^client/(tellus|oceanlab)/' && echo true || echo false)"

cat <<EOF
full=false
server=$server
server_scope=$scope
server_tests=$server_tests
oceanlab_tests=$oceanlab_tests
client=$client
tellus=$(flag '^client/tellus/')
oceanlab_client=$(flag '^client/oceanlab/')
ops=$(grep -vE '\.md$' <<< "$changed" | grep -qE '^(scripts|apps|server)/' && echo true || echo false)
EOF
