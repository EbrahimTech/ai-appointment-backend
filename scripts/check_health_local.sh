#!/bin/bash
# Script to check the health of local services

echo "🔍 Checking local services health..."
echo ""

# Check if services are running
echo "📊 Services Status:"
docker-compose -f docker-compose.local.yml ps
echo ""

# Check backend health
echo "🏥 Backend Health:"
if curl -s http://localhost:8000/health/ > /dev/null; then
    echo "✅ Backend is healthy"
    curl -s http://localhost:8000/health/ | python -m json.tool 2>/dev/null || curl -s http://localhost:8000/health/
else
    echo "❌ Backend health check failed"
fi
echo ""

# Check frontend
echo "🌐 Frontend Accessibility:"
if curl -s http://localhost:3000 > /dev/null; then
    echo "✅ Frontend is accessible at http://localhost:3000"
else
    echo "❌ Frontend is not accessible"
fi
echo ""

# Check nginx
echo "🔧 Nginx:"
if curl -s http://localhost > /dev/null; then
    echo "✅ Nginx is accessible at http://localhost"
else
    echo "❌ Nginx is not accessible"
fi
echo ""

echo "✅ Health check complete!"


