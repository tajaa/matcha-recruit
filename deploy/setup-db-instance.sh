#!/bin/bash
set -e

INSTANCE_IP="3.101.83.217"
KEY_FILE="roonMT-arm.pem"
BACKUP_SCRIPT="deploy/backup-to-s3.sh"
REMOTE_SCRIPT="/home/ec2-user/backup-to-s3.sh"

# Ensure permissions on key
chmod 400 "$KEY_FILE"

echo "Copying backup script to $INSTANCE_IP..."
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no "$BACKUP_SCRIPT" "ec2-user@$INSTANCE_IP:$REMOTE_SCRIPT"

echo "Setting up Cron Job on instance..."
ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no "ec2-user@$INSTANCE_IP" "bash -s" <<EOF
    chmod +x $REMOTE_SCRIPT
    
    # Check if cron job exists
    if ! crontab -l 2>/dev/null | grep -q "$REMOTE_SCRIPT"; then
        # Run every 6 hours
        (crontab -l 2>/dev/null; echo "0 */6 * * * $REMOTE_SCRIPT >> /home/ec2-user/backup.log 2>&1") | crontab -
        echo "Cron job added."
    else
        echo "Cron job already exists."
    fi
    
    # Run backup once to test
    echo "Running initial backup..."
    $REMOTE_SCRIPT
EOF

echo "Setup Complete!"
