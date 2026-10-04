# Sourced by scripts that shell out to host psql/pg_dump/pg_restore.
# Homebrew's libpq is keg-only, so those tools are not on PATH by default.
if ! command -v psql >/dev/null 2>&1; then
  for _libpq in /opt/homebrew/opt/libpq/bin /usr/local/opt/libpq/bin; do
    if [[ -x "$_libpq/psql" ]]; then PATH="$_libpq:$PATH"; break; fi
  done
  unset _libpq
fi
