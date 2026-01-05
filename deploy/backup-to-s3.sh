#!/bin/bash
set -e

# Configuration
BUCKET="s3://matcha-recruit-backups/postgres"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="/tmp/pg_backups"
CONTAINER="matcha-postgres"
DB_USER="matcha"

mkdir -p "$BACKUP_DIR"

# Check if docker is running
if ! docker ps | grep -q "$CONTAINER"; then
    echo "Error: Container $CONTAINER is not running!"
    exit 1
fi

# 1. List databases (excluding templates and postgres system db if desired, keeping postgres for now)
DBS=$(docker exec $CONTAINER psql -U $DB_USER -t -c "SELECT datname FROM pg_database WHERE datistemplate = false;" | tr -d '\r' | xargs)

# 2. Loop and Dump
for DB in $DBS; do
    # Skip empty lines or whitespace
    if [ -z "$DB" ]; then continue; fi
    
    echo "Backing up database: $DB"
    FILENAME="${DB}_${TIMESTAMP}.sql.gz"
    FILEPATH="$BACKUP_DIR/$FILENAME"
    
    # Dump and compress
    if docker exec $CONTAINER pg_dump -U $DB_USER "$DB" | gzip > "$FILEPATH"; then
        echo "  Dump successful. Uploading to S3..."
        
        # Upload
        if aws s3 cp "$FILEPATH" "$BUCKET/$FILENAME"; then
            echo "  Upload successful: $BUCKET/$FILENAME"
            rm "$FILEPATH"
        else
            echo "  Error: Upload failed for $DB"
        fi
    else
        echo "  Error: Dump failed for $DB"
        rm -f "$FILEPATH"
    fi
done

echo "Backup process finished at $(date)"
