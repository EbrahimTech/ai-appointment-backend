# Development Dockerfile
# For production, use Dockerfile.prod instead
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=backend.settings

# Development server - DO NOT USE IN PRODUCTION
# For production, build with: docker build -f Dockerfile.prod -t app:prod .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
