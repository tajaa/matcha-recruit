#!/bin/bash
# Install systemd timer for scheduled worker runs
# Run this on EC2: sudo ./deploy/install-worker-timer.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing Matcha worker timer..."

# Make worker script executable
chmod +x "$PROJECT_DIR/scripts/worker-cycle.sh"

# Copy systemd files
sudo cp "$SCRIPT_DIR/matcha-worker.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/matcha-worker.timer" /etc/systemd/system/

# Update paths in service file to match actual location
sudo sed -i "s|/home/ec2-user/matcha|$PROJECT_DIR|g" /etc/systemd/system/matcha-worker.service

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable matcha-worker.timer
sudo systemctl start matcha-worker.timer

echo "Timer installed! Status:"
sudo systemctl status matcha-worker.timer --no-pager
