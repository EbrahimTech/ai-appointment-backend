#!/bin/bash
# Health check script for AI Appointment Backend
# This script checks if all services are healthy

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

echo "🏥 Health Check - AI Appointment Backend"
echo "========================================"
echo "Backend URL: $BACKEND_URL"
echo ""

# Check health endpoint
echo "1. Checking health endpoint..."
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health/" || echo "000")
if [ "$HEALTH_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✅ Health endpoint: OK${NC}"
else
    echo -e "${RED}❌ Health endpoint: FAILED (HTTP $HEALTH_RESPONSE)${NC}"
    exit 1
fi

# Check readiness endpoint
echo "2. Checking readiness endpoint..."
READY_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/ready/" || echo "000")
if [ "$READY_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✅ Readiness endpoint: OK${NC}"
else
    echo -e "${YELLOW}⚠️  Readiness endpoint: FAILED (HTTP $READY_RESPONSE)${NC}"
    echo "   This might indicate database or cache issues"
fi

# Check database connection (if Django shell is available)
echo "3. Checking database connection..."
if command -v python3 &> /dev/null && [ -f manage.py ]; then
    python3 manage.py check --database default 2>/dev/null && \
        echo -e "${GREEN}✅ Database connection: OK${NC}" || \
        echo -e "${YELLOW}⚠️  Database connection: Check failed${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot check database (Django not available)${NC}"
fi

# Check Redis connection (if redis-cli is available)
echo "4. Checking Redis connection..."
if command -v redis-cli &> /dev/null; then
    redis-cli ping 2>/dev/null | grep -q PONG && \
        echo -e "${GREEN}✅ Redis connection: OK${NC}" || \
        echo -e "${YELLOW}⚠️  Redis connection: FAILED${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot check Redis (redis-cli not available)${NC}"
fi

echo ""
echo "========================================"
echo -e "${GREEN}✅ Health check complete!${NC}"
echo ""

