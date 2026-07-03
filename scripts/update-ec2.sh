#!/bin/bash

################################################################################
# Update EC2 Deployment Script
# Pulls latest images and restarts containers for specified app(s)
################################################################################

set -e

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
    --frontend       Update only matcha-frontend (no DB backup, no worker stop)
    --backend        Update only matcha-backend + matcha-worker
    --agent          Deploy/update agent (Gemini API)
    --all            Update matcha + agent
    --status         Show status of all containers
    -h, --help       Show this help message

EXAMPLES:
    $0 --matcha          # Update only Matcha (all services)
    $0 --frontend        # Frontend-only rollout (fast, no backup)
    $0 --backend         # Backend + worker only
    $0 --all             # Update matcha + agent
    $0 --agent           # Deploy/restart agent
    $0 --status          # Check container status
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
    log_info "Backing up database before deployment..."
    ssh_cmd "bash ~/backup-postgres.sh >> ~/backup.log 2>&1" && \
        log_success "Database backup complete!" || \
        log_warn "Backup may have failed - check ~/backup.log on EC2"
}

pre_cleanup() {
    log_info "Freeing up disk space before pull..."
    if [ "$UPDATE_BACKEND" = true ]; then
        # Gracefully stop workers with 60s timeout to let them finish current job
        log_info "Stopping workers gracefully (60s timeout)..."
        ssh_cmd "docker stop -t 60 matcha-worker 2>/dev/null || true"
        ssh_cmd "docker rm matcha-worker 2>/dev/null || true"
    fi
    # Remove all stopped containers
    ssh_cmd "docker container prune -f" || true
    # Remove ALL unused images (not just dangling) - running containers keep their images
    ssh_cmd "docker image prune -a -f" || true
    # Remove build cache
    ssh_cmd "docker builder prune -f" || true
    # Show available space
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

    if [ "$UPDATE_BACKEND" = true ]; then
        # matcha-worker isn't in the request path — no need to blue-green it,
        # pre_cleanup() already stops it gracefully (60s) before this runs.
        ssh_cmd "cd ~/matcha && docker-compose --profile worker pull matcha-worker && docker-compose --profile worker up -d --no-deps matcha-worker"
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
    log_info "Cleaning up unused images..."
    ssh_cmd "docker system prune -f"
}

# Parse arguments
UPDATE_BACKEND=false
UPDATE_FRONTEND=false
UPDATE_AGENT=false
SHOW_STATUS=false

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
# Frontend-only rollouts don't touch the DB — skip the backup for speed.
if [ "$UPDATE_BACKEND" = true ]; then
    backup_database
fi
pre_cleanup

if [ "$UPDATE_MATCHA" = true ]; then
    # Nginx config (incl. the blue/green frontend upstream block) must be live
    # before the frontend swap script runs against it.
    sync_nginx
    update_matcha
fi

if [ "$UPDATE_AGENT" = true ]; then
    deploy_agent
fi

cleanup
show_status

log_success "Deployment complete!"
