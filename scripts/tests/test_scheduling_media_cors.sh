#!/usr/bin/env bash
# No AWS calls: a stub CLI exercises safe CORS merging and apply boundaries.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cors_test_dir="$(mktemp -d)"
trap 'rm -rf "$cors_test_dir"' EXIT
mkdir "$cors_test_dir/bin"
cat > "$cors_test_dir/bin/aws" <<'AWS'
#!/usr/bin/env bash
set -euo pipefail
case "$2" in
  get-bucket-cors)
    case "$CORS_TEST_MODE" in
      denied) echo 'An error occurred (AccessDenied) when calling GetBucketCors' >&2; exit 255 ;;
      missing) echo 'An error occurred (NoSuchCORSConfiguration) when calling GetBucketCors' >&2; exit 255 ;;
      existing) printf '{"CORSRules":[{"AllowedOrigins":["https://legacy.example.com"],"AllowedMethods":["GET"]}]}\n' ;;
      duplicate) cat "$CORS_TEST_PROPOSAL" ;;
      malformed) echo '{"CORSRules":null}' ;;
      almost_full|full)
        python3 - "$CORS_TEST_MODE" <<'PY'
import json, sys
count = 99 if sys.argv[1] == 'almost_full' else 100
print(json.dumps({'CORSRules': [{'AllowedOrigins': [f'https://rule-{i}.example.com'], 'AllowedMethods': ['GET']} for i in range(count)]}))
PY
        ;;
    esac ;;
  put-bucket-cors)
    printf '%s\n' "$*" >> "$CORS_TEST_WRITES"
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == --cors-configuration ]]; then cp "${2#file://}" "$CORS_TEST_APPLIED"; break; fi
      shift
    done ;;
  *) exit 2 ;;
esac
AWS
chmod +x "$cors_test_dir/bin/aws"
export PATH="$cors_test_dir/bin:$PATH"
export CORS_TEST_PROPOSAL="$repo_root/deploy/s3-cors-scheduling-commercial.json"
export CORS_TEST_WRITES="$cors_test_dir/writes"
export CORS_TEST_APPLIED="$cors_test_dir/applied.json"
export TMPDIR="$cors_test_dir"
cors_script="$repo_root/deploy/configure-scheduling-media-cors.sh"

CORS_TEST_MODE=existing "$cors_script" public-bucket > "$cors_test_dir/proposal.json" 2> "$cors_test_dir/output"
[[ ! -f "$CORS_TEST_WRITES" ]]
python3 - "$cors_test_dir/proposal.json" <<'PY'
import json, sys
rules = json.load(open(sys.argv[1]))['CORSRules']
assert len(rules) == 2
assert rules[0]['AllowedOrigins'] == ['https://legacy.example.com']
assert 'https://hey-matcha.com' in rules[1]['AllowedOrigins']
assert 'POST' in rules[1]['AllowedMethods']
PY
CORS_TEST_MODE=duplicate "$cors_script" public-bucket > "$cors_test_dir/duplicate.json" 2> "$cors_test_dir/output"
python3 - "$cors_test_dir/duplicate.json" <<'PY'
import json, sys
assert len(json.load(open(sys.argv[1]))['CORSRules']) == 1
PY
CORS_TEST_MODE=almost_full "$cors_script" public-bucket > "$cors_test_dir/max.json" 2> "$cors_test_dir/output"
python3 - "$cors_test_dir/max.json" <<'PY'
import json, sys
assert len(json.load(open(sys.argv[1]))['CORSRules']) == 100
PY
CORS_TEST_MODE=missing "$cors_script" public-bucket --apply > "$cors_test_dir/output" 2> "$cors_test_dir/error"
[[ $(wc -l < "$CORS_TEST_WRITES") -eq 1 ]]
[[ -f "$CORS_TEST_APPLIED" ]]
python3 - "$CORS_TEST_APPLIED" <<'PY'
import json, sys
assert 'POST' in json.load(open(sys.argv[1]))['CORSRules'][0]['AllowedMethods']
PY
cors_backups=("$cors_test_dir"/scheduling-media-cors-backup.*)
cors_backup="${cors_backups[0]}"
[[ -f "$cors_backup" ]]
python3 - "$cors_backup" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == {'CORSRules': []}
PY
for mode in denied malformed full; do
  if CORS_TEST_MODE="$mode" "$cors_script" public-bucket --apply > "$cors_test_dir/output" 2> "$cors_test_dir/error"; then exit 1; fi
  [[ $(wc -l < "$CORS_TEST_WRITES") -eq 1 ]]
done
if "$cors_script" public-bucket --bad-option > "$cors_test_dir/output" 2> "$cors_test_dir/error"; then exit 1; fi
echo 'PASS: dry-run, preservation, duplicate rules, rule limits, missing CORS, backups, permission failures, invalid configuration, and explicit apply'
