import hashlib
import hmac
from datetime import datetime, timedelta

import pytest
from django.conf import settings

from apps.clinics.models import Clinic, ClinicService, LanguageChoices
from apps.patients.models import Patient
from apps.patients.utils import normalize_phone_number


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(
        name="Prime Dental",
        slug="prime-dental",
        timezone="UTC",
    )


@pytest.fixture
def clinic_service(clinic):
    return ClinicService.objects.create(
        clinic=clinic,
        code="consult",
        name="Consultation",
        language=LanguageChoices.ENGLISH,
        duration_minutes=30,
    )


@pytest.fixture
def patient(clinic):
    return Patient.objects.create(
        clinic=clinic,
        full_name="John Doe",
        language=LanguageChoices.ENGLISH,
        phone_number="+15555550100",
        normalized_phone=normalize_phone_number("+15555550100"),
    )


@pytest.fixture
def hmac_signature():
    def _sign(payload: bytes) -> str:
        return hmac.new(settings.LEAD_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()

    return _sign
