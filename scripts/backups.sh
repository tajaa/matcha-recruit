#!/bin/bash
# View and manage database backups in S3.
#
# Post DB/app split (2026-05): Postgres lives on the DB host 3.101.83.217 as two
# containers — matcha-postgres-prod (:5433, PROD) and matcha-postgres (:5432, DEV
# + 8 other apps). The canonical twice-daily backup is the host cron
# /home/ec2-user/backup-to-s3.sh, which dumps prod matcha as matcha_* and the
# dev/legacy copy as matcha_test_*. This script is a thin convenience CLI around
# that bucket; `create` delegates to the host script rather than reimplementing it.
set -euo pipefail

S3_BUCKET="s3://matcha-recruit-backups/postgres"
SSH_KEY="${SSH_KEY:-roonMT-arm.pem}"
EC2_HOST="${EC2_HOST:-ec2-user@3.101.83.217}"   # DB host (was app host pre-split)
PROD_CONTAINER="matcha-postgres-prod"
DEV_CONTAINER="matcha-postgres"

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'

ssh_db() { ssh -i "$SSH_KEY" "$EC2_HOST" "$@"; }

usage() {
    cat <<EOF
Usage: $0 [COMMAND]

Commands:
    list          List all backups in S3 (default)
    latest        Show the latest backup per database
    create        Run the canonical host backup now (~/backup-to-s3.sh)
    download F    Download backup file F to the current directory
    restore       Restore a backup into a container DB (interactive, dev by default)
    size          Show total backup storage size

Notes:
    matcha_*       = PRODUCTION matcha (from $PROD_CONTAINER)
    matcha_test_*  = dev/legacy matcha (from $DEV_CONTAINER)
EOF
}

list_backups() {
    echo -e "${BLUE}Backups in S3:${NC}\n"
    ssh_db "aws s3 ls $S3_BUCKET/ --human-readable" | awk '{printf "  %-12s %-10s %s\n", $3, $4, $5}'
    echo -e "\n${BLUE}Total files:${NC} $(ssh_db "aws s3 ls $S3_BUCKET/" | wc -l | tr -d ' ')"
}

latest_backups() {
    echo -e "${BLUE}Latest backups:${NC}\n"
    for db in matcha matcha_test drooli ahnimal; do
        # match "<db>_YYYY-" exactly so matcha doesn't swallow matcha_test
        local line
        line=$(ssh_db "aws s3 ls $S3_BUCKET/" | grep -E " ${db}_[0-9]{4}-" | tail -1 || true)
        [ -n "$line" ] && echo -e "  ${GREEN}${db}:${NC}  $(echo "$line" | awk '{print $4, "(" $3 ")"}')"
    done
}

create_backup() {
    echo -e "${BLUE}Running canonical host backup (~/backup-to-s3.sh) on $EC2_HOST...${NC}"
    ssh_db "bash ~/backup-to-s3.sh"
    echo -e "${GREEN}Done.${NC}\n"
    latest_backups
}

download_backup() {
    local FILENAME="${1:-}"
    [ -n "$FILENAME" ] || { echo -e "${RED}Specify a backup filename (see: $0 list)${NC}"; exit 1; }
    echo -e "${BLUE}Downloading $FILENAME...${NC}"
    ssh_db "aws s3 cp $S3_BUCKET/$FILENAME -" > "$FILENAME"
    echo -e "${GREEN}Downloaded ./$FILENAME${NC}"
}

restore_backup() {
    echo -e "${YELLOW}Available backups:${NC}\n"
    ssh_db "aws s3 ls $S3_BUCKET/" | awk '{print "  " $4}'
    echo
    read -r -p "Backup filename to restore: " FILENAME
    [ -n "$FILENAME" ] || { echo -e "${RED}No filename provided${NC}"; exit 1; }

    read -r -p "Target container [${DEV_CONTAINER}]: " CONTAINER
    CONTAINER="${CONTAINER:-$DEV_CONTAINER}"

    # DB name: strip trailing _YYYY-..., then normalize matcha_test -> matcha
    local DB_NAME
    DB_NAME=$(echo "$FILENAME" | sed -E 's/_[0-9]{4}-.*$//')
    [ "$DB_NAME" = "matcha_test" ] && DB_NAME="matcha"

    echo -e "${YELLOW}Will restore '$FILENAME' into ${CONTAINER} : DB '${DB_NAME}'.${NC}"
    if [[ "$CONTAINER" == *prod* ]]; then
        echo -e "${RED}*** THIS TARGETS PRODUCTION. This overwrites live customer data. ***${NC}"
        read -r -p "Type the container name to confirm prod restore: " C2
        [ "$C2" = "$CONTAINER" ] || { echo "Aborted."; exit 0; }
    fi
    read -r -p "Proceed? (yes/no): " CONFIRM
    [ "$CONFIRM" = "yes" ] || { echo "Aborted."; exit 0; }

    echo -e "${BLUE}Restoring (gunzip | psql)...${NC}"
    ssh_db "aws s3 cp $S3_BUCKET/$FILENAME - | gunzip | docker exec -i $CONTAINER psql -U matcha -d $DB_NAME"
    echo -e "${GREEN}Restore complete.${NC}"
}

show_size() {
    echo -e "${BLUE}Backup storage usage:${NC}"
    ssh_db "aws s3 ls $S3_BUCKET/ --summarize --human-readable" | tail -2
}

case "${1:-list}" in
    list)              list_backups ;;
    latest)            latest_backups ;;
    create)            create_backup ;;
    download)          download_backup "${2:-}" ;;
    restore)           restore_backup ;;
    size)              show_size ;;
    -h|--help|help)    usage ;;
    *)                 echo -e "${RED}Unknown command: $1${NC}"; usage; exit 1 ;;
esac
