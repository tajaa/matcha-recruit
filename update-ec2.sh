#!/bin/bash

################################################################################
# Update EC2 Deployment Script
# Pulls latest images and restarts containers for specified app(s)
################################################################################

set -e

# Configuration
EC2_HOST="ec2-13-52-75-8.us-west-1.compute.amazonaws.com"
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
    --oceaneca       Update Oceaneca/Drooli (ports 8001/8080)
    --all            Update all apps
    --status         Show status of all containers
    -h, --help       Show this help message

EXAMPLES:
    $0 --matcha          # Update only Matcha
    $0 --oceaneca        # Update only Oceaneca
    $0 --all             # Update both apps
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

update_matcha() {
    log_info "Updating Matcha-Recruit..."

    # Only restart app containers, not shared infrastructure (postgres, redis)
    ssh_cmd "cd ~/matcha && docker-compose pull && docker-compose up -d --no-deps matcha-backend matcha-frontend"

    # Restart worker if running
    ssh_cmd "docker restart matcha-worker 2>/dev/null || true"

    log_success "Matcha-Recruit updated!"
}

update_oceaneca() {
    log_info "Updating Oceaneca..."

    # Pull new images
    ssh_cmd "cd ~ && docker-compose pull"

    # Recreate app containers only (they use external matcha network)
    ssh_cmd "docker rm -f oceaneca-backend oceaneca-frontend 2>/dev/null || true"
    ssh_cmd "cd ~ && docker-compose up -d"

    # Restart worker with updated env
    ssh_cmd "docker rm -f drooli-worker 2>/dev/null || true"
    ssh_cmd "docker run -d --name drooli-worker --network matcha_matcha-network --env-file ~/.env --restart unless-stopped 010438494410.dkr.ecr.us-west-1.amazonaws.com/oceaneca-backend:latest sh -c 'PYTHONPATH=/app celery -A workers.celery_app worker --loglevel=info --concurrency=1'"

    log_success "Oceaneca updated!"
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
UPDATE_OCEANECA=false
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
        --oceaneca)
            UPDATE_OCEANECA=true
            shift
            ;;
        --all)
            UPDATE_MATCHA=true
            UPDATE_OCEANECA=true
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

if [ "$UPDATE_MATCHA" = false ] && [ "$UPDATE_OCEANECA" = false ]; then
    log_error "No app specified. Use --matcha, --oceaneca, or --all"
    exit 1
fi

ecr_login

if [ "$UPDATE_MATCHA" = true ]; then
    update_matcha
fi

if [ "$UPDATE_OCEANECA" = true ]; then
    update_oceaneca
fi

cleanup
show_status

log_success "Deployment complete!"
