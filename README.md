# AI Appointment Backend

Backend for AI-driven dental appointment scheduling. Modules cover clinics, patients, WhatsApp channels, dialog FSM, LLM guardrails (DeepSeek), Google Calendar integration, and Celery workers for reminders/outbox.

## Backend Local Development

```bash
python -m venv bot_venv
bot_venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

### Docker Compose

```bash
make dev-up
make dev-down
```

### Celery Beat

```bash
make beat-up
make beat-down
```

Set `CELERY_SWEEP_TENTATIVE_SECONDS` (defaults to 600 seconds) to control how frequently tentative Google appointments are retried.

### WhatsApp Sandbox Test Send

Whitelist sandbox numbers per clinic via `WHATSAPP_TEST_ALLOWLIST` (JSON map of clinic slugs to phone arrays, e.g. `{"demo-dental":["+15555550123"],"*":["+15555550999"]}`) and adjust rate limits with `WHATSAPP_TEST_RPM` (defaults to 3 sends per minute). Attempts outside the allowlist or limit are rejected and audited automatically.

### HQ Support Sessions

OPS and SUPERADMIN staff can impersonate a clinic temporarily:

```bash
curl -H "Authorization: Bearer <hq-jwt>" ^
     -H "Content-Type: application/json" ^
     -X POST https://api.example.com/hq/support/start ^
     -d "{\"clinic_id\":42,\"reason\":\"Investigate escalation\"}"
```

The response returns `support_token` (valid for `SUPPORT_SESSION_MINUTES`, default 15). Use it as a bearer token on read-only clinic endpoints or `POST /clinic/{slug}/conversations/{id}/reply` (templates only). Stop the session explicitly via `/hq/support/stop`. All support traffic is audited; write APIs outside template replies remain blocked during impersonation.

## Frontend (Next.js App Router)

The `frontend/` directory hosts the HQ + clinic portal built with Next.js (App Router), Tailwind, shadcn/ui, React Query, Zod, and next-intl.

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_BACKEND_URL` (defaults to `http://localhost:8000`). Authentication flows through `/api/session/login`, storing JWTs in httpOnly cookies. After choosing a clinic at `/select-clinic`, the `clinicSlug` cookie is persisted and users are redirected to `/c/[slug]/dashboard`. Middleware protects `/hq` and `/c/[slug]`, ensuring valid cookies before granting access.

## Testing

```bash
pytest
```

## Environment

Copy `.env.example` to `.env` and adjust DeepSeek, Google OAuth, WhatsApp provider, encryption key, and other secrets.
