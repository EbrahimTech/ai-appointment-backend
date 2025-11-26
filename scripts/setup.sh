#!/bin/bash
# Setup script for AI Appointment Backend
# This script helps set up the project for deployment

set -e

echo "🚀 AI Appointment Backend - Setup Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found${NC}"
    if [ -f env.example ]; then
        echo "📋 Copying env.example to .env..."
        cp env.example .env
        echo -e "${GREEN}✅ Created .env file${NC}"
        echo -e "${YELLOW}⚠️  Please edit .env and fill in your values!${NC}"
    else
        echo -e "${RED}❌ env.example not found!${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Check Python version
echo ""
echo "🐍 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Check if virtual environment exists
if [ ! -d "bot_venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv bot_venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
echo ""
echo "🔌 Activating virtual environment..."
source bot_venv/bin/activate || source bot_venv/Scripts/activate

# Install dependencies
echo ""
echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if PostgreSQL is available
echo ""
echo "🗄️  Checking database connection..."
if python3 -c "import psycopg; print('psycopg available')" 2>/dev/null; then
    echo -e "${GREEN}✅ PostgreSQL driver available${NC}"
else
    echo -e "${YELLOW}⚠️  PostgreSQL driver not available${NC}"
fi

# Create logs directory
echo ""
echo "📁 Creating logs directory..."
mkdir -p logs
echo -e "${GREEN}✅ Logs directory created${NC}"

# Run migrations
echo ""
echo "🔄 Running database migrations..."
python manage.py migrate --noinput || echo -e "${YELLOW}⚠️  Migrations failed (database might not be configured)${NC}"

# Collect static files
echo ""
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput || echo -e "${YELLOW}⚠️  Static files collection failed${NC}"

# Check environment variables
echo ""
echo "🔍 Checking required environment variables..."
REQUIRED_VARS=("DJANGO_SECRET_KEY" "POSTGRES_DB" "POSTGRES_USER" "POSTGRES_PASSWORD")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" .env 2>/dev/null || grep -q "^${var}=$" .env 2>/dev/null || grep -q "^${var}=change-this" .env 2>/dev/null; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ All required variables are set${NC}"
else
    echo -e "${YELLOW}⚠️  Missing or default values for:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    echo -e "${YELLOW}Please update .env file!${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Edit .env file and fill in all required values"
echo "2. Set up WhatsApp ChannelAccount (see WHATSAPP_SETUP.md)"
echo "3. Run: python manage.py seed_data (for initial data)"
echo "4. Start development server: python manage.py runserver"
echo ""

