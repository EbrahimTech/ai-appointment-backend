# AI Appointment Backend

Backend for AI-driven dental appointment setter. Includes modules for clinics, patients, WhatsApp channel orchestration, dialog FSM, LLM guardrails with DeepSeek, Google Calendar integration, and Celery workers for reminders/outbox.

## Local Development

`ash
python -m venv bot_venv
bot_venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver
`

### Docker Compose

`ash
make dev-up
make dev-down
`

### Celery Beat

`ash
make beat-up
make beat-down
`

Set `CELERY_SWEEP_TENTATIVE_SECONDS` (defaults to 600 seconds) to adjust how frequently tentative Google appointments are swept and retried.
العنوان: Sprint 8 – Clinic users/invites & role management (OWNER/ADMIN only)

المحتوى:
Scope: Allow clinic owners/admins to invite members and manage roles.

Endpoints:

GET /clinic/{slug}/users
→ {ok:true, data:{ items:[{id,email,name,role}] }}

POST /clinic/{slug}/users {email, role}
→ creates invite (stub token flow) → {ok:true, data:{id,email,role, invited:true}}

PUT /clinic/{slug}/users/{id} {role}
→ update role

DELETE /clinic/{slug}/users/{id}
→ remove membership

Rules:

OWNER/ADMIN only; STAFF/VIEWER forbidden.

AuditLog for mutations: USER_INVITE, USER_ROLE_UPDATE, USER_REMOVE (scope=CLINIC, meta carries target user id/email).

Validate roles ∈ {OWNER,ADMIN,STAFF,VIEWER}; {ok:false,"error":"INVALID_ROLE"} otherwise.

Tests:

Permissions matrix enforced.

Duplicate invite handled idempotently (same email, same clinic).

Happy paths & error shapes match.
### WhatsApp Sandbox Test Send

Whitelist sandbox numbers per clinic via the `WHATSAPP_TEST_ALLOWLIST` environment variable (JSON map of clinic slugs to phone arrays, e.g. `{"demo-dental":["+15555550123"],"*":["+15555550999"]}`) and adjust the per-clinic rate limit with `WHATSAPP_TEST_RPM` (defaults to 3 sends per minute). Attempts outside the allowlist or limit are rejected and audited automatically.

### HQ Support Sessions

OPS and SUPERADMIN staff can impersonate a clinic temporarily:

```
curl -H "Authorization: Bearer <hq-jwt>" ^
     -H "Content-Type: application/json" ^
     -X POST https://api.example.com/hq/support/start ^
     -d "{\"clinic_id\":42,\"reason\":\"Investigate escalation\"}"
```

The response returns `support_token` (valid for `SUPPORT_SESSION_MINUTES`, default 15). Use it as a bearer token on read-only clinic endpoints or `POST /clinic/{slug}/conversations/{id}/reply` (templates only). Stop the session explicitly:

```
curl -H "Authorization: Bearer <hq-jwt>" ^
     -H "Content-Type: application/json" ^
     -X POST https://api.example.com/hq/support/stop ^
     -d "{\"support_token\":\"<token>\"}"
```

All support traffic is audited automatically; write APIs outside template replies remain blocked during impersonation.

## Testing

`ash
pytest
`

## Environment

Copy .env.example to .env and adjust secrets (DeepSeek, Google OAuth, WhatsApp provider, encryption key, etc.).
