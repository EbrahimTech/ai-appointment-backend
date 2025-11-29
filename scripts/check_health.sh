#!/bin/bash
# Script to check health of all services
# Usage: ./scripts/check_health.sh

set -e

echo "🔍 Checking service health..."
echo ""

# Check if services are running
echo "📦 Docker Services:"
docker-compose -f docker-compose.prod.yml ps
echo ""

# Check backend health
echo "🏥 Backend Health:"
if curl -f -s http://localhost/health/ > /dev/null 2>&1; then
    echo "✅ Backend is healthy"
    curl -s http://localhost/health/ | python -m json.tool
else
    echo "❌ Backend health check failed"
    exit 1
fi
echo ""

# Check database connection
echo "🗄️  Database Connection:"
docker-compose -f docker-compose.prod.yml exec -T web python manage.py check --database default 2>&1 | grep -q "System check identified no issues" && echo "✅ Database connection OK" || echo "❌ Database connection failed"
echo ""

# Check Redis connection
echo "📮 Redis Connection:"
docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping 2>&1 | grep -q "PONG" && echo "✅ Redis connection OK" || echo "❌ Redis connection failed"
echo ""

# Check Celery worker
echo "⚙️  Celery Worker:"
if docker-compose -f docker-compose.prod.yml exec -T worker celery -A backend inspect ping 2>&1 | grep -q "pong"; then
    echo "✅ Celery worker is running"
else
    echo "⚠️  Celery worker may not be responding"
fi
echo ""

echo "✅ Health check complete!"

