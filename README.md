# AI Appointment Backend

Backend for AI-driven dental appointment scheduling. Modules cover clinics, patients, WhatsApp channels, dialog FSM, LLM guardrails (DeepSeek), Google Calendar integration, and Celery workers for reminders/outbox.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Backend Local Development](#backend-local-development)
- [Frontend Development](#frontend-development)
- [Docker Compose](#docker-compose)
- [Production Deployment](#production-deployment)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Documentation](#documentation)

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop (for Docker Compose)
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Local Development with Docker

```bash
# 1. Clone the repository
git clone <repository-url>
cd ai-appointment-backend

# 2. Copy environment file
cp env.example .env
# Edit .env with your settings

# 3. Start all services
make dev-up

# 4. Run migrations
make migrate

# 5. Seed initial data (optional)
make seed

# 6. Access the application
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
```

---

## 🔧 Backend Local Development

### Without Docker

```bash
# 1. Create virtual environment
python -m venv bot_venv
bot_venv\Scripts\activate  # Windows
# or
source bot_venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp env.example .env
# Edit .env with your settings

# 4. Run migrations
python manage.py migrate

# 5. Seed initial data (optional)
python manage.py seed_data

# 6. Start development server
python manage.py runserver
```

### Docker Compose Commands

```bash
# Start all services
make dev-up
# or
docker-compose up -d

# Stop all services
make dev-down
# or
docker-compose down

# Access Django shell
make dev-shell
# or
docker-compose exec web bash

# Run migrations
make migrate
# or
docker-compose exec web python manage.py migrate

# Seed data
make seed
# or
docker-compose exec web python manage.py seed_data

# Run tests
make test
# or
docker-compose exec web pytest
```

### Celery Beat

```bash
# Start Celery Beat
make beat-up
# or
docker-compose up -d beat

# Stop Celery Beat
make beat-down
# or
docker-compose stop beat
```

Set `CELERY_SWEEP_TENTATIVE_SECONDS` (defaults to 600 seconds) to control how frequently tentative Google appointments are retried.

---

## 🎨 Frontend (Next.js App Router)

The `frontend/` directory hosts the HQ + clinic portal built with Next.js (App Router), Tailwind, shadcn/ui, React Query, Zod, and next-intl.

### Local Development

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_BACKEND_URL` in `.env.local` (defaults to `http://localhost:8000`).

### Authentication Flow

Authentication flows through `/api/session/login`, storing JWTs in httpOnly cookies. After choosing a clinic at `/select-clinic`, the `clinicSlug` cookie is persisted and users are redirected to `/c/[slug]/dashboard`. Middleware protects `/hq` and `/c/[slug]`, ensuring valid cookies before granting access.

---

## 🐳 Production Deployment

### Prerequisites

- Server with Docker and Docker Compose installed
- Domain name configured
- SSL certificates (Let's Encrypt recommended)

### Deployment Steps

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd ai-appointment-backend
   cp env.example .env
   # Edit .env with production values
   ```

2. **Generate Secrets**
   ```bash
   make generate-secrets
   # Copy the generated secrets to .env
   ```

3. **Setup SSL Certificates**
   ```bash
   # Using Let's Encrypt
   sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com
   mkdir -p ssl
   sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
   sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem
   sudo chmod 644 ssl/cert.pem
   sudo chmod 600 ssl/key.pem
   ```

4. **Build and Start**
   ```bash
   make prod-build
   make prod-up
   make prod-migrate
   ```

5. **Create HQ Admin User**
   ```bash
   make create-hq-user
   # Or manually:
   # make create-hq-user admin@yourdomain.com YourPassword123! SUPERADMIN
   ```

6. **Check Health**
   ```bash
   make health
   ```

### Production Commands

```bash
# Build production images
make prod-build

# Start production services
make prod-up

# Stop production services
make prod-down

# View logs
make prod-logs

# Access Django shell
make prod-shell

# Run migrations
make prod-migrate

# Check service health
make health

# Backup database
make backup

# Create HQ user
make create-hq-user [email] [password] [role]
```

### Updating Production

```bash
# 1. Pull latest changes
git pull

# 2. Rebuild images
make prod-build

# 3. Restart services
make prod-down
make prod-up

# 4. Run migrations (if needed)
make prod-migrate
```

---

## 🔐 Environment Variables

See `env.example` for a complete list of all environment variables with descriptions.

### Required Variables

- `DJANGO_SECRET_KEY` - Django secret key (generate with `make generate-secrets`)
- `POSTGRES_PASSWORD` - Database password
- `REDIS_PASSWORD` - Redis password
- `ENCRYPTION_KEY` - Encryption key (generate with `make generate-secrets`)
- `LEAD_WEBHOOK_SECRET` - Webhook secret (generate with `make generate-secrets`)

### Optional Variables

- `DEEPSEEK_API_KEY` - For LLM features
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - For Google Calendar integration
- `WHATSAPP_DEFAULT_SENDER` - For WhatsApp integration

Generate secure secrets:
```bash
make generate-secrets
```

---

## 🧪 Testing

```bash
# Run all tests
make test
# or
docker-compose exec web pytest

# Run specific test file
docker-compose exec web pytest tests/test_auth.py

# Run with coverage
docker-compose exec web pytest --cov=apps
```

---

## 📚 Documentation

- **Testing Guide**: See `TESTING_GUIDE.md` for complete instructions on running the full stack for testing and deployment.
- **Security Review**: See `SECURITY_REVIEW.md` for security configuration details.
- **Environment Variables**: See `env.example` for all available environment variables.

---

## 🔑 Key Features

### WhatsApp Integration

Whitelist sandbox numbers per clinic via `WHATSAPP_TEST_ALLOWLIST` (JSON map of clinic slugs to phone arrays, e.g. `{"demo-dental":["+15555550123"],"*":["+15555550999"]}`) and adjust rate limits with `WHATSAPP_TEST_RPM` (defaults to 3 sends per minute). Attempts outside the allowlist or limit are rejected and audited automatically.

### HQ Support Sessions

OPS and SUPERADMIN staff can impersonate a clinic temporarily:

```bash
curl -H "Authorization: Bearer <hq-jwt>" \
     -H "Content-Type: application/json" \
     -X POST https://api.example.com/hq/support/start \
     -d '{"clinic_id":42,"reason":"Investigate escalation"}'
```

The response returns `support_token` (valid for `SUPPORT_SESSION_MINUTES`, default 60). Use it as a bearer token on read-only clinic endpoints or `POST /clinic/{slug}/conversations/{id}/reply` (templates only). Stop the session explicitly via `/hq/support/stop`. All support traffic is audited; write APIs outside template replies remain blocked during impersonation.

### Roles & Permissions

- **OWNER**: Full access to their clinic only
- **ADMIN**: Full administrative access to clinic
- **STAFF**: Can create appointments and reply to conversations
- **VIEWER**: Read-only access
- **SUPERADMIN (HQ)**: Full access to all clinics
- **OPS (HQ)**: Read-only access to all clinics

---

## 🛠️ Maintenance

### Database Backup

```bash
make backup
# Backups are stored in ./backups/ directory
# Last 7 backups are kept automatically
```

### Health Checks

```bash
make health
# Checks all services: backend, database, Redis, Celery
```

### Logs

```bash
# View all logs
make prod-logs

# View specific service logs
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f worker
```

---

## 📝 License

[Add your license here]

---

## 🤝 Contributing

[Add contributing guidelines here]

---

## 📞 Support

[Add support contact information here]
