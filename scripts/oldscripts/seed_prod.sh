#!/bin/bash
# Seed the production database with IR test data

EC2_HOST="54.177.107.107"
EC2_USER="ec2-user"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY="${SCRIPT_DIR}/../roonMT-arm.pem"

echo "Connecting to production ($EC2_HOST) to seed IR incidents..."

ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" "docker exec matcha-backend python scripts/seed_ir_incidents.py"

echo "Done."
