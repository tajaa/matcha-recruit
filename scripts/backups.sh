#!/bin/bash
# View and manage database backups in S3

set -e

S3_BUCKET="s3://matcha-recruit-backups/postgres"
SSH_KEY="${SSH_KEY:-roonMT-arm.pem}"
EC2_HOST="ec2-user@54.177.107.107"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    cat << EOF
Usage: $0 [COMMAND]

Commands:
    list          List all backups in S3 (default)
    latest        Show the latest backup for each database
    create        Create a new backup now
    download      Download a backup file
    restore       Restore from a backup (interactive)
    size          Show total backup storage size

Examples:
    $0                     # List all backups
    $0 list                # List all backups
    $0 latest              # Show latest backups
    $0 create              # Create backup now
    $0 download matcha_2025-12-30_18-33-49.sql.gz
EOF
}

list_backups() {
    echo -e "${BLUE}Backups in S3:${NC}"
    echo ""
    ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 ls $S3_BUCKET/ --human-readable" | \
        awk '{printf "  %-12s %-10s %s\n", $3, $4, $5}'
    echo ""
    echo -e "${BLUE}Total files:${NC} $(ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 ls $S3_BUCKET/" | wc -l | tr -d ' ')"
}

latest_backups() {
    echo -e "${BLUE}Latest backups:${NC}"
    echo ""

    # Get latest matcha backup
    MATCHA=$(ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 ls $S3_BUCKET/ | grep matcha | tail -1")
    if [ -n "$MATCHA" ]; then
        echo -e "  ${GREEN}matcha:${NC}  $(echo "$MATCHA" | awk '{print $4, "(" $3 ")"}')"
    fi

    # Get latest drooli backup
    DROOLI=$(ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 ls $S3_BUCKET/ | grep drooli | tail -1")
    if [ -n "$DROOLI" ]; then
        echo -e "  ${GREEN}drooli:${NC}  $(echo "$DROOLI" | awk '{print $4, "(" $3 ")"}')"
    fi
}

create_backup() {
    # Encrypted path: when BACKUP_GPG_PASSPHRASE is set, the dump is run
    # inline over SSH with `pg_dump | gzip | gpg --symmetric` and uploaded
    # with SSE-KMS. Without the passphrase, fall back to the legacy
    # host-side `~/backup-postgres.sh` (unencrypted gzip). The legacy path
    # is kept for backward compat — once the cron on the host is migrated,
    # delete the else-branch.
    local DB="${1:-matcha}"
    if [ -n "$BACKUP_GPG_PASSPHRASE" ]; then
        local DATE=$(date +%F_%H-%M-%S)
        local FILENAME="${DB}_${DATE}.sql.gz.gpg"
        echo -e "${BLUE}Creating encrypted backup ${FILENAME}...${NC}"
        # Escape the passphrase for the remote shell; tee through gpg's
        # --passphrase-fd 0 to avoid leaking it via process listing.
        ssh -i "$SSH_KEY" "$EC2_HOST" "\
            export PASSPHRASE='$BACKUP_GPG_PASSPHRASE'; \
            pg_dump -U matcha $DB | gzip | \
            gpg --symmetric --cipher-algo AES256 --batch \
                --passphrase \"\$PASSPHRASE\" | \
            aws s3 cp - $S3_BUCKET/$FILENAME --sse aws:kms"
        unset PASSPHRASE
        echo -e "${GREEN}Encrypted backup complete:${NC} $S3_BUCKET/$FILENAME"
    else
        echo -e "${YELLOW}BACKUP_GPG_PASSPHRASE unset — running legacy unencrypted backup.${NC}"
        echo -e "${YELLOW}Set the env var (or pull from Secrets Manager) to enable encryption.${NC}"
        ssh -i "$SSH_KEY" "$EC2_HOST" "bash ~/backup-postgres.sh"
        echo -e "${GREEN}Backup complete!${NC}"
    fi
    echo ""
    latest_backups
}

download_backup() {
    if [ -z "$1" ]; then
        echo -e "${RED}Error: Specify backup filename${NC}"
        echo "Example: $0 download matcha_2025-12-30_18-33-49.sql.gz.gpg"
        exit 1
    fi

    FILENAME="$1"
    echo -e "${BLUE}Downloading $FILENAME...${NC}"
    ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 cp $S3_BUCKET/$FILENAME -" > "$FILENAME"
    echo -e "${GREEN}Downloaded to ./$FILENAME${NC}"

    case "$FILENAME" in
        *.gpg)
            echo -e "${YELLOW}File is GPG-encrypted. To decrypt locally:${NC}"
            echo "  BACKUP_GPG_PASSPHRASE=... gpg --batch --decrypt --passphrase \"\$BACKUP_GPG_PASSPHRASE\" $FILENAME > ${FILENAME%.gpg}"
            ;;
    esac
}

restore_backup() {
    echo -e "${YELLOW}Available backups:${NC}"
    echo ""
    ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 ls $S3_BUCKET/" | awk '{print NR") " $4}'
    echo ""
    read -p "Enter backup filename to restore: " FILENAME

    if [ -z "$FILENAME" ]; then
        echo -e "${RED}No filename provided${NC}"
        exit 1
    fi

    # Extract database name from filename
    DB_NAME=$(echo "$FILENAME" | sed 's/_[0-9].*$//')

    echo -e "${YELLOW}WARNING: This will restore $FILENAME to database '$DB_NAME'${NC}"
    read -p "Are you sure? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi

    case "$FILENAME" in
        *.gpg)
            if [ -z "$BACKUP_GPG_PASSPHRASE" ]; then
                echo -e "${RED}BACKUP_GPG_PASSPHRASE required to restore encrypted backup${NC}"
                exit 1
            fi
            echo -e "${BLUE}Restoring (decrypt + gunzip + psql)...${NC}"
            ssh -i "$SSH_KEY" "$EC2_HOST" "\
                export PASSPHRASE='$BACKUP_GPG_PASSPHRASE'; \
                aws s3 cp $S3_BUCKET/$FILENAME - | \
                gpg --batch --decrypt --passphrase \"\$PASSPHRASE\" | \
                gunzip | docker exec -i matcha-postgres psql -U matcha -d $DB_NAME"
            ;;
        *)
            echo -e "${BLUE}Restoring (gunzip + psql)...${NC}"
            ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 cp $S3_BUCKET/$FILENAME - | gunzip | docker exec -i matcha-postgres psql -U matcha -d $DB_NAME"
            ;;
    esac
    echo -e "${GREEN}Restore complete!${NC}"
}

show_size() {
    echo -e "${BLUE}Backup storage usage:${NC}"
    ssh -i "$SSH_KEY" "$EC2_HOST" "aws s3 ls $S3_BUCKET/ --summarize --human-readable" | tail -2
}

# Main
COMMAND="${1:-list}"

case "$COMMAND" in
    list)
        list_backups
        ;;
    latest)
        latest_backups
        ;;
    create)
        create_backup
        ;;
    download)
        download_backup "$2"
        ;;
    restore)
        restore_backup
        ;;
    size)
        show_size
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        usage
        exit 1
        ;;
esac
