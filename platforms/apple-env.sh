# Sourced by the platforms/**/release*.sh scripts — loads App Store Connect API
# credentials from the repo so nothing has to be exported in ~/.zshrc.
#
#   secrets/apple.env          untracked; holds APPLE_API_ISSUER_ID (see apple.env.example)
#   secrets/AuthKey_<ID>.p8    untracked; APPLE_API_KEY_ID defaults to <ID>
#
# Variables already set in the caller's environment always win. Never prints values.

_apple_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$_apple_root" ]]; then
    if [[ -f "$_apple_root/secrets/apple.env" ]]; then
        while IFS='=' read -r _k _v; do
            [[ "$_k" =~ ^[[:space:]]*(export[[:space:]]+)?(APPLE_[A-Z_]+)$ ]] || continue
            _k="${BASH_REMATCH[2]}"
            _v="${_v%\"}"; _v="${_v#\"}"; _v="${_v%\'}"; _v="${_v#\'}"
            [[ -n "${!_k:-}" ]] || export "$_k=$_v"
        done < "$_apple_root/secrets/apple.env"
    fi

    _apple_keys=("$_apple_root"/secrets/AuthKey_*.p8)
    if [[ ${#_apple_keys[@]} -eq 1 && -f "${_apple_keys[0]}" ]]; then
        : "${APPLE_API_KEY_PATH:=${_apple_keys[0]}}"
        _apple_id="$(basename "${_apple_keys[0]}" .p8)"
        : "${APPLE_API_KEY_ID:=${_apple_id#AuthKey_}}"
        export APPLE_API_KEY_PATH APPLE_API_KEY_ID
    fi
fi
unset _apple_root _apple_keys _apple_id _k _v
