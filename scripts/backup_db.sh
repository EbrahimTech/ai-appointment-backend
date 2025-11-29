#!/bin/bash
# Script to backup PostgreSQL database
# Usage: ./scripts/backup_db.sh [output_file]

set -e

BACKUP_DIR=${BACKUP_DIR:-"./backups"}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE=${1:-"${BACKUP_DIR}/backup_${TIMESTAMP}.sql"}

mkdir -p "$BACKUP_DIR"

echo "📦 Creating database backup..."
echo "Output: $OUTPUT_FILE"

# Get database credentials from environment
POSTGRES_DB=${POSTGRES_DB:-"ai_appointment"}
POSTGRES_USER=${POSTGRES_USER:-"ai_user"}

docker-compose -f docker-compose.prod.yml exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$OUTPUT_FILE"

# Compress backup
gzip -f "$OUTPUT_FILE"
COMPRESSED_FILE="${OUTPUT_FILE}.gz"

echo "✅ Backup created: $COMPRESSED_FILE"
echo "📊 Size: $(du -h "$COMPRESSED_FILE" | cut -f1)"

# Keep only last 7 backups
echo "🧹 Cleaning old backups (keeping last 7)..."
ls -t ${BACKUP_DIR}/backup_*.sql.gz | tail -n +8 | xargs -r rm -f

echo "✅ Done!"

