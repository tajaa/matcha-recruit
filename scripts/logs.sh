#!/bin/bash

################################################################################
# Tail production logs — no more hand-typing `docker logs` over ssh and
# guessing which blue-green port suffix is live this week.
#
# Usage:
#   ./scripts/logs.sh backend            # live backend container (8002 or 8003)
#   ./scripts/logs.sh worker             # celery worker
#   ./scripts/logs.sh frontend           # frontend container nginx
#   ./scripts/logs.sh nginx              # HOST nginx access log
#   ./scripts/logs.sh nginx-err          # HOST nginx error log
#   ./scripts/logs.sh errors             # backend log filtered to ERROR/Traceback
#   ./scripts/logs.sh cw /matcha/backend # CloudWatch group (runs locally)
#   ./scripts/logs.sh -n 200 backend     # last 200 lines instead of 100
#
# Full runbook (where every log lives, CW queries, error tables): docs/ops/LOGS.md
################################################################################

set -e

EC2_HOST="54.177.107.107"
EC2_USER="ec2-user"
SSH_KEY="${SSH_KEY:-secrets/roonMT-arm.pem}"
AWS_REGION="${AWS_REGION:-us-west-1}"
TAIL_LINES=100

RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -n has to be parsed before the subcommand so `-n 200 backend` and
# `backend -n 200` both work.
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        -n) TAIL_LINES="$2"; shift 2 ;;
        *)  ARGS+=("$1"); shift ;;
    esac
done
set -- "${ARGS[@]:-}"

ssh_tty() {
    ssh -t -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$EC2_USER@$EC2_HOST" "$1"
}

# Backend and frontend are blue-green'd: the live container is
# matcha-backend-8002 or -8003 depending on which deploy ran last. Resolve it
# by name prefix rather than hardcoding a port that goes stale every deploy.
live_container() {
    echo "docker ps --format '{{.Names}}' | grep '^$1' | head -1"
}

cmd_container_logs() {
    local prefix="$1"
    log_info "Tailing $prefix on $EC2_HOST (Ctrl+C to stop)..."
    ssh_tty "c=\$($(live_container "$prefix")); \
        if [ -z \"\$c\" ]; then echo 'No running container matching $prefix'; exit 1; fi; \
        echo \"--- \$c ---\"; docker logs -f --tail $TAIL_LINES \"\$c\""
}

cmd_errors() {
    log_info "Backend ERROR/Traceback lines (last $TAIL_LINES matches)..."
    ssh_tty "c=\$($(live_container matcha-backend)); \
        if [ -z \"\$c\" ]; then echo 'No running backend container'; exit 1; fi; \
        docker logs \"\$c\" 2>&1 | grep -E 'ERROR|Traceback|\" 5[0-9][0-9] ' | tail -$TAIL_LINES"
}

cmd_nginx() {
    log_info "Host nginx access log (Ctrl+C to stop)..."
    ssh_tty "sudo tail -n $TAIL_LINES -f /var/log/nginx/access.log"
}

cmd_nginx_err() {
    log_info "Host nginx error log (Ctrl+C to stop)..."
    ssh_tty "sudo tail -n $TAIL_LINES -f /var/log/nginx/error.log"
}

# Runs locally against CloudWatch, not over ssh — only useful once shipping is
# enabled (deploy/cloudwatch/README.md).
cmd_cw() {
    local group="${1:-}"
    if [ -z "$group" ]; then
        log_error "Usage: $0 cw <log-group>   e.g. $0 cw /matcha/backend"
        log_info "Groups: /matcha/backend /matcha/frontend /matcha/worker /matcha/nginx-access /matcha/nginx-error"
        exit 1
    fi
    log_info "Tailing CloudWatch group $group (Ctrl+C to stop)..."
    aws logs tail "$group" --follow --region "$AWS_REGION"
}

usage() {
    cat << EOF
Usage: $0 [-n LINES] COMMAND

Tail production logs on the app EC2 ($EC2_HOST).

COMMANDS:
    backend     Live backend container (resolves the 8002/8003 blue-green suffix)
    worker      Celery worker container
    frontend    Frontend container's internal nginx
    nginx       HOST nginx access log (all vhosts)
    nginx-err   HOST nginx error log
    errors      Backend log filtered to ERROR / Traceback / 5xx
    cw GROUP    Tail a CloudWatch Logs group (local aws CLI, not ssh)
    -h,--help   Show this help

OPTIONS:
    -n LINES    Lines of history (default $TAIL_LINES)

Durable error records live in Postgres, not these logs — see the admin UI at
/admin/server-errors and /admin/client-errors. Full runbook: docs/ops/LOGS.md
EOF
}

COMMAND="${1:-}"
case "$COMMAND" in
    backend)   cmd_container_logs matcha-backend ;;
    worker)    cmd_container_logs matcha-worker ;;
    frontend)  cmd_container_logs matcha-frontend ;;
    nginx)     cmd_nginx ;;
    nginx-err) cmd_nginx_err ;;
    errors)    cmd_errors ;;
    cw)        cmd_cw "${2:-}" ;;
    -h|--help) usage ;;
    "")        usage; exit 1 ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
