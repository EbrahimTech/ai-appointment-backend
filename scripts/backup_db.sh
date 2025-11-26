#!/bin/bash
# Database backup script for AI Appointment Backend
# This script creates a backup of the PostgreSQL database

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Database configuration
DB_NAME="${POSTGRES_DB:-ai_appointment}"
DB_USER="${POSTGRES_USER:-ai_user}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

# Backup directory
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql"

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "💾 Database Backup - AI Appointment Backend"
echo "=========================================="
echo "Database: $DB_NAME"
echo "Host: $DB_HOST"
echo "Backup file: $BACKUP_FILE"
echo ""

# Check if pg_dump is available
if ! command -v pg_dump &> /dev/null; then
    echo -e "${YELLOW}⚠️  pg_dump not found. Trying Docker...${NC}"
    
    if command -v docker &> /dev/null; then
        echo "Using Docker to create backup..."
        docker run --rm \
            -e PGPASSWORD="$POSTGRES_PASSWORD" \
            -v "$(pwd)/$BACKUP_DIR:/backups" \
            postgres:15 \
            pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -f "/backups/$(basename $BACKUP_FILE)"
        
        echo -e "${GREEN}✅ Backup created: $BACKUP_FILE${NC}"
    else
        echo "❌ Neither pg_dump nor Docker is available!"
        exit 1
    fi
else
    # Create backup using pg_dump
    echo "Creating backup..."
    PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -F c \
        -f "$BACKUP_FILE"
    
    echo -e "${GREEN}✅ Backup created: $BACKUP_FILE${NC}"
fi

# Compress backup
if command -v gzip &> /dev/null; then
    echo "Compressing backup..."
    gzip "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE}.gz"
    echo -e "${GREEN}✅ Backup compressed: $BACKUP_FILE${NC}"
fi

# Keep only last 7 days of backups
echo "Cleaning old backups (keeping last 7 days)..."
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql*" -mtime +7 -delete 2>/dev/null || true

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Backup complete!${NC}"
echo "Backup location: $BACKUP_FILE"
echo ""

