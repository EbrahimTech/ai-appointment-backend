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

## Testing

`ash
pytest
`

## Environment

Copy .env.example to .env and adjust secrets (DeepSeek, Google OAuth, WhatsApp provider, encryption key, etc.).
