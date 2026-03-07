#!/bin/bash

################################################################################
# Agent CLI — interact with the matcha-agent on EC2
#
# Usage:
#   ./agent.sh              # Interactive chat (default)
#   ./agent.sh chat         # Interactive chat
#   ./agent.sh stop         # Stop agent container
#   ./agent.sh status       # Show agent container status
#   ./agent.sh logs         # Tail agent logs
################################################################################

set -e

EC2_HOST="54.177.107.107"
EC2_USER="ec2-user"
SSH_KEY="${SSH_KEY:-roonMT-arm.pem}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

ssh_cmd() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$EC2_USER@$EC2_HOST" "$1"
}

cmd_chat() {
    log_info "Connecting to agent on EC2..."

    # Run agent CLI interactively with TTY
    ssh -t -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$EC2_USER@$EC2_HOST" \
        "cd ~/matcha && docker-compose --profile agent run --rm --entrypoint python matcha-agent -m agent.cli"
}

cmd_stop() {
    log_info "Stopping agent..."
    ssh_cmd "cd ~/matcha && docker-compose --profile agent stop matcha-agent && docker-compose --profile agent rm -f matcha-agent"
    log_success "Agent stopped."
}

cmd_status() {
    log_info "Agent containers:"
    ssh_cmd "docker ps --filter name=matcha-agent --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo 'No agent containers running'"
    echo ""
    log_info "Memory:"
    ssh_cmd "docker stats --no-stream --filter name=matcha-agent --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' 2>/dev/null || true"
}

cmd_logs() {
    log_info "Tailing agent logs (Ctrl+C to stop)..."
    ssh -t -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$EC2_USER@$EC2_HOST" \
        "cd ~/matcha && docker-compose --profile agent logs -f --tail 50 matcha-agent"
}

usage() {
    cat << EOF
Usage: $0 [COMMAND]

Interact with the matcha-agent running on EC2.

COMMANDS:
    chat       Interactive chat with the agent (default)
    stop       Stop agent container
    status     Show agent container status
    logs       Tail agent logs
    -h,--help  Show this help message
EOF
}

# Default to chat if no args
COMMAND="${1:-chat}"

case "$COMMAND" in
    chat)    cmd_chat ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    -h|--help) usage ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
