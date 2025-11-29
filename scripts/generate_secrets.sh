#!/bin/bash
# Script to generate secure secrets for .env file
# Usage: ./scripts/generate_secrets.sh

echo "🔐 Generating secure secrets..."
echo ""
echo "# Add these to your .env file:"
echo ""

echo "# Django Secret Key:"
python3 -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50))"
echo ""

echo "# Encryption Key:"
python3 -c "import secrets; print('ENCRYPTION_KEY=' + secrets.token_hex(32))"
echo ""

echo "# Webhook Secret:"
python3 -c "import secrets; print('LEAD_WEBHOOK_SECRET=' + secrets.token_urlsafe(32))"
echo ""

echo "# Database Password (16+ chars recommended):"
python3 -c "import secrets; import string; chars = string.ascii_letters + string.digits + string.punctuation; print('POSTGRES_PASSWORD=' + ''.join(secrets.choice(chars) for _ in range(24)))"
echo ""

echo "# Redis Password (16+ chars recommended):"
python3 -c "import secrets; import string; chars = string.ascii_letters + string.digits + string.punctuation; print('REDIS_PASSWORD=' + ''.join(secrets.choice(chars) for _ in range(24)))"
echo ""

echo "✅ Done! Copy these values to your .env file."

