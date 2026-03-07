#!/bin/bash

################################################################################
# Update EC2 Deployment Script
# Pulls latest images and restarts containers for specified app(s)
################################################################################

set -e

# Configuration
EC2_HOST="54.177.107.107"
EC2_USER="ec2-user"
SSH_KEY="${SSH_KEY:-roonMT-arm.pem}"
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
    --matcha         Update Matcha-Recruit (ports 8002/8082)
    --agent          Deploy/update agent + llama (Qwen local LLM)
    --agent-upload   Upload Qwen model to EC2 (one-time, ~508MB)
    --all            Update matcha + agent
    --status         Show status of all containers
    -h, --help       Show this help message

EXAMPLES:
    $0 --matcha          # Update only Matcha
    $0 --all             # Update matcha + agent
    $0 --agent-upload    # Upload Qwen model (first time only)
    $0 --agent           # Deploy/restart agent with local Qwen
    $0 --status          # Check container status
EOF
}

ssh_cmd() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$EC2_USER@$EC2_HOST" "$1"
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
    # Gracefully stop workers with 60s timeout to let them finish current job
    log_info "Stopping workers gracefully (60s timeout)..."
    ssh_cmd "docker stop -t 60 matcha-worker 2>/dev/null || true"
    ssh_cmd "docker rm matcha-worker 2>/dev/null || true"
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
    log_info "Updating Matcha-Recruit..."

    # Only restart app containers, not shared infrastructure (postgres, redis)
    # Use --profile worker so the Celery worker container is also created/started
    ssh_cmd "cd ~/matcha && docker-compose --profile worker pull && docker-compose --profile worker up -d --no-deps matcha-backend matcha-frontend matcha-worker"

    log_success "Matcha-Recruit updated!"
}

upload_model() {
    local model_file="server/agent/models/Qwen3.5-0.8B-Q4_K_M.gguf"
    if [ ! -f "$model_file" ]; then
        log_error "Model file not found: $model_file"
        exit 1
    fi
    log_info "Creating models directory on EC2..."
    ssh_cmd "mkdir -p ~/matcha/models"
    log_info "Uploading Qwen 0.8B model (~508MB)..."
    scp -i "$SSH_KEY" "$model_file" "$EC2_USER@$EC2_HOST:~/matcha/models/"
    log_success "Model uploaded to EC2:~/matcha/models/"
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
UPDATE_MATCHA=false
UPDATE_AGENT=false
AGENT_UPLOAD=false
SHOW_STATUS=false

if [ $# -eq 0 ]; then
    usage
    exit 1
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --matcha)
            UPDATE_MATCHA=true
            shift
            ;;
        --agent)
            UPDATE_AGENT=true
            shift
            ;;
        --agent-upload)
            AGENT_UPLOAD=true
            shift
            ;;
        --all)
            UPDATE_MATCHA=true
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
if [ "$SHOW_STATUS" = true ]; then
    show_status
    exit 0
fi

# Agent-only operations (no backup/cleanup needed)
if [ "$AGENT_UPLOAD" = true ]; then
    upload_model
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
    log_error "No app specified. Use --matcha, --agent, or --all"
    exit 1
fi

ecr_login
backup_database
pre_cleanup

if [ "$UPDATE_MATCHA" = true ]; then
    update_matcha
fi

if [ "$UPDATE_AGENT" = true ]; then
    deploy_agent
fi

cleanup
show_status

log_success "Deployment complete!"
