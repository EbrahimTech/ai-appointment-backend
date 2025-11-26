#!/bin/bash
# Deployment script for AI Appointment Backend
# This script helps deploy the application to production

set -e

echo "🚀 AI Appointment Backend - Deployment Script"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "Please create .env file from env.example"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check if DEBUG is false
if [ "$DJANGO_DEBUG" != "false" ]; then
    echo -e "${RED}❌ DJANGO_DEBUG must be false in production!${NC}"
    exit 1
fi

# Check required variables
echo "🔍 Checking required environment variables..."
REQUIRED_VARS=("DJANGO_SECRET_KEY" "POSTGRES_DB" "POSTGRES_USER" "POSTGRES_PASSWORD" "DJANGO_ALLOWED_HOSTS")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ] || [[ "${!var}" == *"change-this"* ]]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}❌ Missing required variables:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    exit 1
fi

echo -e "${GREEN}✅ All required variables are set${NC}"

# Build Docker image
echo ""
echo "🐳 Building Docker image..."
docker build -f Dockerfile.prod -t ai-appointment-backend:latest .

# Run health check
echo ""
echo "🏥 Running health check..."
docker run --rm --env-file .env ai-appointment-backend:latest python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
print('✅ Database connection OK')
" || echo -e "${YELLOW}⚠️  Health check failed (might be expected if DB not accessible)${NC}"

# Run migrations
echo ""
echo "🔄 Running migrations..."
docker run --rm --env-file .env --network host ai-appointment-backend:latest python manage.py migrate --noinput

# Collect static files
echo ""
echo "📦 Collecting static files..."
docker run --rm --env-file .env ai-appointment-backend:latest python manage.py collectstatic --noinput

echo ""
echo "=============================================="
echo -e "${GREEN}✅ Deployment preparation complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Start services: docker-compose -f docker-compose.prod.yml up -d"
echo "2. Check logs: docker-compose -f docker-compose.prod.yml logs -f"
echo "3. Test health: curl http://localhost/health/"
echo ""

