from datetime import timedelta

from django.conf import settings


def test_sweep_schedule_registered():
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert "sweep-tentative-google-syncs" in schedule
    entry = schedule["sweep-tentative-google-syncs"]
    assert entry["task"] == "apps.workers.tasks.sweep_tentative_google_syncs"
    assert isinstance(entry["schedule"], timedelta)
    assert entry["schedule"].total_seconds() == settings.CELERY_SWEEP_TENTATIVE_SECONDS


def test_sweep_schedule_unique_key():
    keys = [key for key in settings.CELERY_BEAT_SCHEDULE if "sweep-tentative" in key]
    assert keys.count("sweep-tentative-google-syncs") == 1
