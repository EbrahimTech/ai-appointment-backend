# AI Appointment Backend

Django backend for AI-driven dental appointment scheduling with WhatsApp integration, LLM guardrails (DeepSeek), and Google Calendar sync.

## Tech Stack

- **Backend:** Django 4.2, PostgreSQL (pgvector), Redis, Celery
- **Frontend:** Next.js 14 (App Router), Tailwind, React Query
- **Integrations:** WhatsApp (Meta/Twilio), Google Calendar, DeepSeek LLM

## Quick Start

```bash
cp env.example .env
python -m venv bot_venv
source bot_venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

## Development

```bash
# Docker
make dev-up
make dev-down

# Celery Beat
make beat-up
make beat-down

# Frontend
cd frontend && npm install && npm run dev
```

## Production

```bash
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

## Environment Variables

See `env.example` for all required variables. Critical:
- `DJANGO_SECRET_KEY`
- `POSTGRES_*`
- `CELERY_BROKER_URL`
- `DEEPSEEK_API_KEY`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `LEAD_WEBHOOK_SECRET`

## WhatsApp Setup

Create `ChannelAccount` in database:

```python
from apps.channels.models import ChannelAccount
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="meta",  # or "twilio", "generic"
    access_token="TOKEN",
    metadata={"phone_number_id": "ID"}
)
```

## Health Checks

- `/health/` - Basic health
- `/ready/` - Readiness (DB + cache)

## Scripts

- `scripts/setup.sh` - Initial setup
- `scripts/deploy.sh` - Deployment prep
- `scripts/health_check.sh` - Health verification
- `scripts/backup_db.sh` - Database backup

## Testing

```bash
pytest
```

## Documentation

See `GUIDE.md` for complete deployment guide and detailed documentation.
