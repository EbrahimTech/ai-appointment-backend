import json
from datetime import time

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ClinicMembership
from apps.clinics.models import Clinic, ClinicService, ServiceHours
from apps.templates.models import MessageTemplate

pytestmark = pytest.mark.django_db


def _create_clinic():
    return Clinic.objects.create(slug="demo", name="Demo", tz="UTC", default_lang="en")


def _make_user(django_user_model, clinic, email, role):
    user = django_user_model.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="First",
        last_name="Last",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _put_json(client, path, payload, user, token):
    client.defaults["REMOTE_ADDR"] = f"10.0.0.{token % 250 + 1}"
    return client.put(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        **_auth_headers(user),
    )


def _get(client, path, user):
    client.defaults["REMOTE_ADDR"] = "10.0.1.1"
    return client.get(path, **_auth_headers(user))


def test_services_put_requires_admin(client, django_user_model):
    clinic = _create_clinic()
    service = ClinicService.objects.create(
        clinic=clinic,
        code="clean",
        name="Cleaning",
        duration_minutes=30,
        language="en",
    )
    staff = _make_user(django_user_model, clinic, "staff@example.com", ClinicMembership.Role.STAFF)
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)

    get_resp = _get(client, f"/clinic/{clinic.slug}/services", staff)
    assert get_resp.status_code == 200
    assert get_resp.json()["ok"] is True

    forbidden = _put_json(
        client,
        f"/clinic/{clinic.slug}/services",
        {"services": [{"code": "clean", "name": "Cleaning", "duration_minutes": 45}]},
        staff,
        1,
    )
    assert forbidden.status_code == 403
    assert forbidden.json() == {"ok": False, "error": "FORBIDDEN"}

    response = _put_json(
        client,
        f"/clinic/{clinic.slug}/services",
        {
            "services": [
                {
                    "code": "clean",
                    "name": "Pro Cleaning",
                    "description": "Deep clean",
                    "duration_minutes": 45,
                    "language": "en",
                    "is_active": False,
                },
                {
                    "code": "whiten",
                    "name": "Whitening",
                    "duration_minutes": 30,
                    "language": "en",
                },
            ]
        },
        admin,
        2,
    )
    assert response.status_code == 200
    data = response.json()["data"]["items"]
    assert any(item["code"] == "clean" and item["duration_minutes"] == 45 and item["is_active"] is False for item in data)
    assert any(item["code"] == "whiten" for item in data)
    service.refresh_from_db()
    assert service.name == "Pro Cleaning"
    assert ClinicService.objects.filter(code="whiten").exists()


def test_hours_put_validation(client, django_user_model):
    clinic = _create_clinic()
    service = ClinicService.objects.create(
        clinic=clinic,
        code="clean",
        name="Cleaning",
        duration_minutes=30,
        language="en",
    )
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)
    viewer = _make_user(django_user_model, clinic, "viewer@example.com", ClinicMembership.Role.VIEWER)

    get_resp = _get(client, f"/clinic/{clinic.slug}/hours", viewer)
    assert get_resp.status_code == 200

    bad = _put_json(
        client,
        f"/clinic/{clinic.slug}/hours",
        {
            "hours": [
                {"service_code": "clean", "weekday": 1, "start_time": "09:00", "end_time": "12:00"},
                {"service_code": "clean", "weekday": 1, "start_time": "11:00", "end_time": "13:00"},
            ]
        },
        admin,
        3,
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "INVALID_HOURS"

    good = _put_json(
        client,
        f"/clinic/{clinic.slug}/hours",
        {
            "hours": [
                {"service_code": "clean", "weekday": 1, "start_time": "09:00", "end_time": "12:00"},
                {"service_code": "clean", "weekday": 1, "start_time": "13:00", "end_time": "17:00"},
            ]
        },
        admin,
        4,
    )
    assert good.status_code == 200
    items = good.json()["data"]["items"]
    assert len(items) == 2
    assert ServiceHours.objects.filter(service=service).count() == 2


def test_templates_put_lint_and_permissions(client, django_user_model):
    clinic = _create_clinic()
    template = MessageTemplate.objects.create(
        clinic=clinic,
        code="greet",
        language="en",
        body="Hi {{name}}",
        variables=["name"],
        provider_template_id="greet",
        category="whatsapp",
    )
    viewer = _make_user(django_user_model, clinic, "viewer@example.com", ClinicMembership.Role.VIEWER)
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)

    list_resp = _get(client, f"/clinic/{clinic.slug}/templates", viewer)
    assert list_resp.status_code == 200

    forbidden = _put_json(
        client,
        f"/clinic/{clinic.slug}/templates",
        {"templates": [{"key": "greet", "lang": "en", "enabled": False}]},
        viewer,
        5,
    )
    assert forbidden.status_code == 403

    lint_fail = _put_json(
        client,
        f"/clinic/{clinic.slug}/templates",
        {"templates": [{"key": "greet", "lang": "en", "variables": ["unknown"]}]},
        admin,
        6,
    )
    assert lint_fail.status_code == 400
    assert lint_fail.json()["error"] == "LINT_FAILED"

    ok = _put_json(
        client,
        f"/clinic/{clinic.slug}/templates",
        {"templates": [{"key": "greet", "lang": "en", "enabled": False, "variables": ["name"]}]},
        admin,
        7,
    )
    assert ok.status_code == 200
    template.refresh_from_db()
    assert template.is_active is False
