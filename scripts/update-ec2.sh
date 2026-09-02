#!/bin/bash

################################################################################
# Update EC2 Deployment Script
# Pulls latest images and restarts containers for specified app(s)
################################################################################

set -e

# This deploys to live prod. The agent sandbox is otherwise capable of
# running it (ssh/aws creds are reachable there — see
# docs/ops/AGENT_SANDBOX.md), so require an explicit opt-in rather than
# letting a no-approval agent deploy by default.
case "${AGENT_SANDBOX:-${CODEX_SANDBOX:-}}" in
    1|true|TRUE|yes|YES)
        if [[ "${SANDBOX_ALLOW_DEPLOY:-}" != "1" ]]; then
            echo "update-ec2.sh deploys to live prod. Set SANDBOX_ALLOW_DEPLOY=1 to run it from the agent sandbox, or run it on the host." >&2
            exit 1
        fi
        ;;
esac

# Always operate from the repo root so relative paths (secrets/, docker-compose.yml,
# scripts/deploy-*.sh) resolve regardless of the caller's CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

# Configuration
EC2_HOST="54.177.107.107"
EC2_USER="ec2-user"
SSH_KEY="${SSH_KEY:-secrets/roonMT-arm.pem}"
AWS_REGION="us-west-1"
AWS_ACCOUNT_ID="010438494410"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Update EC2 deployments by pulling latest images and restarting containers.

OPTIONS:
    --matcha         Update Matcha-Recruit backend + frontend + worker (ports 8002/8082)
    --frontend       Update only matcha-frontend (no backup trigger, no worker stop)
    --backend        Update only matcha-backend + matcha-worker
    --hotfix         Fast path: skip nginx sync, skip backup trigger, skip all
                     pruning, 5s worker stop. Pull + blue/green swap only.
    --agent          Deploy/update agent (Gemini API)
    --all            Update matcha + agent
    --status         Show status of all containers
    -h, --help       Show this help message

EXAMPLES:
    $0 --matcha            # Update only Matcha (all services)
    $0 --frontend          # Frontend-only rollout (fast, no backup)
    $0 --backend           # Backend + worker only
    $0 --backend --hotfix  # Emergency backend patch — fastest possible swap
    $0 --all               # Update matcha + agent
    $0 --agent             # Deploy/restart agent
    $0 --status            # Check container status

NOTES:
    Backend deploys enqueue a self-hosted Postgres logical backup through
    pg-backup.service and never wait on it. The same service runs twice daily.
    Dumps stream to s3://matcha-recruit-backups/postgres-selfhosted/; there is
    no RDS PITR for live prod. Check ~/backup.log on EC2 for dump status.
EOF
}

ssh_cmd() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$EC2_USER@$EC2_HOST" "$1"
}

sync_nginx() {
    # matcha.conf's upstream blocks `include` these files (the blue/green
    # active ports for frontend + backend). They live under
    # /etc/nginx/upstream/ (NOT conf.d/) so nginx's automatic conf.d/*.conf
    # glob does NOT pick them up at http context — a bare `server 127.0.0.1:8002;`
    # is valid inside upstream{} but causes "directive 'server' has no opening
    # '{}'" when nginx tries to parse it at http level.
    ssh_cmd "sudo mkdir -p /etc/nginx/upstream"
    ssh_cmd "[ -f /etc/nginx/upstream/matcha-frontend-active.conf ] || echo 'server 127.0.0.1:8082;' | sudo tee /etc/nginx/upstream/matcha-frontend-active.conf > /dev/null"
    ssh_cmd "[ -f /etc/nginx/upstream/matcha-backend-active.conf ] || echo 'server 127.0.0.1:8002;' | sudo tee /etc/nginx/upstream/matcha-backend-active.conf > /dev/null"
    # Clean up any stale active-conf files in conf.d/ from the old layout
    ssh_cmd "sudo rm -f /etc/nginx/conf.d/matcha-backend-active.conf /etc/nginx/conf.d/matcha-frontend-active.conf"

    log_info "Syncing nginx config (deploy/nginx/*.conf)..."
    for f in deploy/nginx/*.conf; do
        scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$f" \
            "$EC2_USER@$EC2_HOST:/tmp/$(basename "$f")"
        ssh_cmd "sudo cp /etc/nginx/conf.d/$(basename "$f") /etc/nginx/conf.d/$(basename "$f").bak-\$(date +%Y%m%d-%H%M%S) 2>/dev/null; sudo mv /tmp/$(basename "$f") /etc/nginx/conf.d/$(basename "$f")"
    done
    if ssh_cmd "sudo nginx -t" ; then
        ssh_cmd "sudo nginx -s reload"
        log_success "nginx config synced + reloaded"
    else
        log_error "nginx -t failed on EC2 — config NOT reloaded, previous config still serving. Check /etc/nginx/conf.d/*.bak-* to diff."
        exit 1
    fi
}

ecr_login() {
    log_info "Logging into ECR..."
    ssh_cmd "aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
}

backup_database() {
    # Install the canonical service every normal backend deploy so the host
    # timer cannot drift back to the retired container script. --no-block
    # queues this deploy's extra run without making the rollout wait for it.
    # The script's flock handles a timer/deploy collision safely.
    log_info "Installing backup timer and triggering logical backup (non-blocking)..."
    if scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
            deploy/backup-prod.sh deploy/pg-backup.service deploy/pg-backup.timer \
            "$EC2_USER@$EC2_HOST:/tmp/" \
        && ssh_cmd "sudo install -m 0755 /tmp/backup-prod.sh /home/ec2-user/backup-prod.sh && sudo install -m 0644 /tmp/pg-backup.service /etc/systemd/system/pg-backup.service && sudo install -m 0644 /tmp/pg-backup.timer /etc/systemd/system/pg-backup.timer && sudo systemctl daemon-reload && sudo systemctl enable --now pg-backup.timer && sudo systemctl start --no-block pg-backup.service"
    then
        log_success "Backup queued; twice-daily timer installed (check ~/backup.log)"
    else
        log_warn "Could not install or trigger backup — deploy continues; check pg-backup.service"
    fi
}

install_worker_timer() {
    # The host's stale scripts/worker-cycle.sh STOPS the worker after 300s — it
    # predates the continuous-worker design. Remove that one known copy so it
    # stops firing on this host, then install the recycle timer that re-fires
    # @worker_ready. (This only deletes the hardcoded path below — it doesn't
    # guarantee the script can't be reintroduced some other way.)
    log_info "Installing worker recycle timer..."
    if scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
            deploy/matcha-worker.service deploy/matcha-worker.timer \
            "$EC2_USER@$EC2_HOST:/tmp/" \
        && ssh_cmd "sudo rm -f /home/ec2-user/matcha/scripts/worker-cycle.sh && sudo install -m 0644 /tmp/matcha-worker.service /etc/systemd/system/matcha-worker.service && sudo install -m 0644 /tmp/matcha-worker.timer /etc/systemd/system/matcha-worker.timer && rm -f /tmp/matcha-worker.service /tmp/matcha-worker.timer && sudo systemctl daemon-reload && sudo systemctl enable --now matcha-worker.timer"
    then
        log_success "Worker recycle timer installed"
    else
        log_warn "Could not install worker recycle timer — deploy continues"
    fi
}

pre_cleanup() {
    if [ "$UPDATE_BACKEND" = true ]; then
        # Gracefully stop workers to let them finish current job.
        # 60s normally; 5s on --hotfix (an emergency patch outranks an
        # in-flight research task, which retries anyway via acks_late).
        local stop_timeout=60
        [ "$HOTFIX" = true ] && stop_timeout=5
        log_info "Stopping workers gracefully (${stop_timeout}s timeout)..."
        ssh_cmd "docker stop -t $stop_timeout matcha-worker 2>/dev/null || true"
        ssh_cmd "docker rm matcha-worker 2>/dev/null || true"
    fi
    if [ "$HOTFIX" = true ]; then
        return 0
    fi
    # Remove stopped containers only. The aggressive `image prune -a` that
    # used to run HERE was the single biggest deploy-time cost: it deleted
    # every cached layer BEFORE the pull, forcing a cold full-image pull on
    # every single deploy. Image/builder pruning now happens post-swap in
    # cleanup(), where it doesn't sit between you and the new code.
    ssh_cmd "docker container prune -f" || true
    # Safety valve: if disk is critically low (<4GB), prune images pre-pull
    # anyway — a failed pull from ENOSPC is worse than a slow one. Sanitized:
    # non-numeric output (ssh banner/warning) must neither abort the deploy
    # (set -e + integer-test error) nor collapse to 0 and silently prune on
    # every deploy (which restores the cold-pull cost this exists to remove).
    local avail_kb
    avail_kb=$(ssh_cmd "df -k / | tail -1 | awk '{print \$4}'" 2>/dev/null | tr -dc '0-9' || true)
    if [[ "$avail_kb" =~ ^[0-9]+$ ]]; then
        if [ "$avail_kb" -lt 4194304 ]; then
            log_warn "Low disk (<4GB) — pruning images before pull"
            ssh_cmd "docker image prune -a -f" || true
            ssh_cmd "docker builder prune -f" || true
        fi
    else
        log_warn "Could not read remote disk space — skipping low-disk prune check"
    fi
    ssh_cmd "df -h / | tail -1 | awk '{print \"Available disk space: \" \$4}'"
}

update_matcha() {
    log_info "Updating Matcha-Recruit (backend=${UPDATE_BACKEND} frontend=${UPDATE_FRONTEND})..."

    # Sync docker-compose.yml from repo so live host config can't drift from
    # source (memory limits, env vars, profiles). Without this, hand-edits to
    # ~/matcha/docker-compose.yml on EC2 silently override repo defaults
    # forever — which is how matcha-backend stayed pinned at 384M for months
    # while the repo said 1g. Still needed even though matcha-backend/
    # matcha-frontend are blue-green'd now: docker-compose.yml is the source
    # of truth for image refs, memory limits, etc that the blue-green scripts
    # don't independently track, and matcha-worker still deploys via compose.
    log_info "Syncing docker-compose.yml..."
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new docker-compose.yml \
        "$EC2_USER@$EC2_HOST:~/matcha/docker-compose.yml"
    # Worker CloudWatch-logging override. Only takes effect when the host's
    # .env sets MATCHA_LOG_DRIVER=awslogs (see the compose_files shell snippet
    # below and deploy/cloudwatch/README.md) — syncing it unconditionally just
    # keeps the host copy current.
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new docker-compose.logging.yml \
        "$EC2_USER@$EC2_HOST:~/matcha/docker-compose.logging.yml"

    if [ "$UPDATE_BACKEND" = true ]; then
        # matcha-worker isn't in the request path — no need to blue-green it,
        # pre_cleanup() already stops it gracefully (60s) before this runs.
        # The compose_files list picks up the awslogs override only when the
        # host opted in; otherwise the worker stays on json-file.
        ssh_cmd "cd ~/matcha && compose_files='-f docker-compose.yml' && grep -qs '^MATCHA_LOG_DRIVER=awslogs' .env && compose_files=\"\$compose_files -f docker-compose.logging.yml\"; docker-compose \$compose_files --profile worker pull matcha-worker && docker-compose \$compose_files --profile worker up -d --no-deps matcha-worker"
        deploy_backend_zero_downtime
    fi

    if [ "$UPDATE_FRONTEND" = true ]; then
        deploy_frontend_zero_downtime
    fi

    log_success "Matcha-Recruit updated!"
}

deploy_backend_zero_downtime() {
    log_info "Deploying backend (blue/green — no downtime)..."
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new scripts/deploy-backend-bluegreen.sh \
        "$EC2_USER@$EC2_HOST:~/matcha/deploy-backend-bluegreen.sh"
    ssh_cmd "chmod +x ~/matcha/deploy-backend-bluegreen.sh && bash ~/matcha/deploy-backend-bluegreen.sh"
    log_success "Backend swapped with zero downtime!"
}

deploy_frontend_zero_downtime() {
    log_info "Deploying frontend (blue/green — no downtime)..."
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new scripts/deploy-frontend-bluegreen.sh \
        "$EC2_USER@$EC2_HOST:~/matcha/deploy-frontend-bluegreen.sh"
    ssh_cmd "chmod +x ~/matcha/deploy-frontend-bluegreen.sh && bash ~/matcha/deploy-frontend-bluegreen.sh"
    log_success "Frontend swapped with zero downtime!"
}


deploy_agent() {
    log_info "Deploying agent API..."
    ssh_cmd "cd ~/matcha && docker-compose --profile agent pull matcha-agent && docker-compose --profile agent up -d matcha-agent"
    log_success "Agent API deployed on port 9100!"
}

show_status() {
    log_info "Container status:"
    ssh_cmd "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    echo ""
    log_info "Memory usage:"
    ssh_cmd "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'"
}

cleanup() {
    # Post-swap prune: running containers keep their images, so this reclaims
    # the old blue/green side + stale layers WITHOUT forcing the next deploy
    # to cold-pull (registry layers unchanged since this deploy stay cached
    # in the retained running images).
    log_info "Cleaning up unused images (post-swap)..."
    ssh_cmd "docker image prune -a -f" || true
    ssh_cmd "docker builder prune -f" || true
}

trigger_post_deploy_automations() {
    local target="$1"
    local deployed_at deploy_id sha source
    deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # Follow-up ancestry checks need the immutable full object id. A short SHA
    # is operator-friendly but not an authoritative cross-checkout identity.
    sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    deploy_id="${sha:0:12}-$(date -u +%Y%m%d%H%M%S)"
    source="laptop"
    [ "${GITHUB_ACTIONS:-}" = "true" ] && source="github"

    # Both follow-ups happen after the production swap. A missing gh session,
    # token, or temporary GitHub outage must never turn a healthy swap into a
    # failed deploy; each workflow reports its own authoritative failure.
    if ! command -v gh >/dev/null 2>&1; then
        log_warn "Post-deploy automations not dispatched: gh CLI is unavailable"
        return 0
    fi
    if gh workflow run post-deploy-error-regression.yml --ref main \
        -f deploy_id="$deploy_id" \
        -f deployed_at="$deployed_at" \
        -f target="$target" \
        -f sha="$sha" \
        -f source="$source"
    then
        log_success "Post-deploy error monitor dispatched ($deploy_id)"
    else
        log_warn "Could not dispatch post-deploy error monitor; deploy remains successful"
    fi

    if gh workflow run admin-updates-autopublish.yml --ref main \
        -f deploy_id="$deploy_id" \
        -f deployed_at="$deployed_at" \
        -f target="$target" \
        -f sha="$sha" \
        -f source="$source"
    then
        log_success "Production admin-update publisher dispatched ($deploy_id)"
    else
        log_warn "Could not dispatch production admin-update publisher; deploy remains successful"
    fi

    if gh workflow run post-deploy-fix-verification.yml --ref main \
        -f deploy_id="$deploy_id" \
        -f deployed_at="$deployed_at" \
        -f target="$target" \
        -f sha="$sha" \
        -f source="$source"
    then
        log_success "Post-deploy AutoPR fix verification dispatched ($deploy_id)"
    else
        log_warn "Could not dispatch post-deploy AutoPR fix verification; deploy remains successful"
    fi
}

# Parse arguments
UPDATE_BACKEND=false
UPDATE_FRONTEND=false
UPDATE_AGENT=false
SHOW_STATUS=false
HOTFIX=false

if [ $# -eq 0 ]; then
    usage
    exit 1
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --matcha)
            UPDATE_BACKEND=true
            UPDATE_FRONTEND=true
            shift
            ;;
        --frontend)
            UPDATE_FRONTEND=true
            shift
            ;;
        --backend)
            UPDATE_BACKEND=true
            shift
            ;;
        --hotfix)
            HOTFIX=true
            shift
            ;;
        --agent)
            UPDATE_AGENT=true
            shift
            ;;
        --all)
            UPDATE_BACKEND=true
            UPDATE_FRONTEND=true
            UPDATE_AGENT=true
            shift
            ;;
        --status)
            SHOW_STATUS=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Execute
UPDATE_MATCHA=false
if [ "$UPDATE_BACKEND" = true ] || [ "$UPDATE_FRONTEND" = true ]; then
    UPDATE_MATCHA=true
fi

if [ "$SHOW_STATUS" = true ]; then
    show_status
    exit 0
fi

if [ "$UPDATE_AGENT" = true ] && [ "$UPDATE_MATCHA" = false ]; then
    ecr_login
    deploy_agent
    show_status
    log_success "Agent deployment complete!"
    exit 0
fi

if [ "$UPDATE_MATCHA" = false ] && [ "$UPDATE_AGENT" = false ]; then
    log_error "No app specified. Use --matcha, --frontend, --backend, --agent, or --all"
    exit 1
fi

ecr_login
# Frontend-only rollouts don't touch the DB; hotfixes skip the trigger too
# (it's non-blocking anyway, but --hotfix means "nothing but the swap").
if [ "$UPDATE_BACKEND" = true ] && [ "$HOTFIX" = false ]; then
    backup_database
fi
pre_cleanup

if [ "$UPDATE_MATCHA" = true ]; then
    # Nginx config (incl. the blue/green frontend upstream block) must be live
    # before the frontend swap script runs against it. Hotfix path assumes
    # nginx config is already current (it survives deploys unchanged).
    if [ "$HOTFIX" = false ]; then
        sync_nginx
    fi
    update_matcha
fi

# Installed/enabled after the swap, not before pre_cleanup — enabling a
# previously-inactive timer fires it immediately (elapsed OnBootSec), and
# pre_cleanup is about to stop/rm the very container that would restart.
if [ "$UPDATE_BACKEND" = true ] && [ "$HOTFIX" = false ]; then
    install_worker_timer
fi

if [ "$UPDATE_AGENT" = true ]; then
    deploy_agent
fi

if [ "$HOTFIX" = false ]; then
    cleanup
fi
show_status

if [ "$UPDATE_MATCHA" = true ]; then
    if [ "$UPDATE_BACKEND" = true ] && [ "$UPDATE_FRONTEND" = true ]; then
        trigger_post_deploy_automations matcha
    elif [ "$UPDATE_BACKEND" = true ]; then
        trigger_post_deploy_automations backend
    else
        trigger_post_deploy_automations frontend
    fi
fi

# Test tenants (Sunset Smile Dental Group, 720 Behavioral, Onc, ...) stay in
# sync dev<->prod by riding every normal deploy — see scripts/sync_tenants.py
# for the merge engine and scripts/sync-test-tenants.sh for the wrapper this
# calls. Skipped on --hotfix (nothing but the swap) and when only --agent was
# deployed (UPDATE_MATCHA false means no backend/frontend code moved).
# Never fails the deploy: a sync problem is surfaced, not blocking.
if [ "$HOTFIX" = false ] && [ "$UPDATE_MATCHA" = true ]; then
    if [ "${CI:-}" = "true" ] || [ "${GITHUB_ACTIONS:-}" = "true" ]; then
        # GH Actions runner has no local dev Postgres — the sync would quietly
        # no-op anyway (--auto treats dev-unreachable as a skip); say so
        # explicitly instead of relying on that.
        log_info "Tenant sync skipped in CI (needs local dev DB) — run ./scripts/sync-test-tenants.sh from the laptop."
        # $GITHUB_STEP_SUMMARY renders in the Actions tab and the GitHub
        # mobile app — the two places a dispatched deploy is actually watched
        # from, so put the reminder where it won't be missed.
        if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
            {
                echo "### Test-tenant sync pending"
                echo
                echo "Deployed from CI, which has no local dev Postgres. Run on the Mac:"
                echo
                echo '```'
                echo './scripts/sync-test-tenants.sh --auto'
                echo '```'
            } >> "$GITHUB_STEP_SUMMARY"
        fi
    else
        log_info "Syncing test tenants (dev <-> prod)..."
        "$(dirname "$0")/sync-test-tenants.sh" --auto \
            || log_warn "Test-tenant sync failed (deploy unaffected). Run ./scripts/sync-test-tenants.sh manually."
    fi
fi

log_success "Deployment complete!"
