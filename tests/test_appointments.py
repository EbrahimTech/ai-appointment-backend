from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus

pytestmark = pytest.mark.django_db


def make_slot(start: datetime, minutes: int = 30):
    return (start, start + timedelta(minutes=minutes))


def test_double_booking_exclusion(clinic, clinic_service, patient):
    if connection.vendor != "postgresql":
        pytest.skip("Range exclusion requires PostgreSQL backend")

    start = timezone.now()
    Appointment.objects.create(
        clinic=clinic,
        service=clinic_service,
        patient=patient,
        slot=make_slot(start),
        status=AppointmentStatus.BOOKED,
    )

    with pytest.raises(IntegrityError):
        Appointment.objects.create(
            clinic=clinic,
            service=clinic_service,
            patient=patient,
            slot=make_slot(start + timedelta(minutes=5)),
            status=AppointmentStatus.BOOKED,
        )


def test_concurrent_booking_race_condition(clinic, clinic_service, patient):
    if connection.vendor != "postgresql":
        pytest.skip("Concurrency test requires PostgreSQL backend")

    slot_range = make_slot(timezone.now())

    def attempt_booking():
        try:
            with transaction.atomic():
                Appointment.objects.create(
                    clinic=clinic,
                    service=clinic_service,
                    patient=patient,
                    slot=slot_range,
                    status=AppointmentStatus.BOOKED,
                )
            return True
        except IntegrityError:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: attempt_booking(), range(10)))

    assert sum(results) == 1
    assert (
        Appointment.objects.filter(
            clinic=clinic, service=clinic_service, status=AppointmentStatus.BOOKED
        ).count()
        == 1
    )
