import json

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, ClinicMembership, StaffAccount
from apps.clinics.models import Clinic

pytestmark = pytest.mark.django_db


def _make_user(django_user_model, email: str = "admin@example.com"):
    user = django_user_model.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Admin",
        last_name="User",
        is_active=True,
    )
    return user


def _seed_membership(user, clinic_slug="demo-dental"):
    clinic = Clinic.objects.create(
        slug=clinic_slug,
        name="Demo Dental",
        tz="Europe/Istanbul",
        default_lang="ar",
    )
    ClinicMembership.objects.create(
        user=user,
        clinic=clinic,
        role=ClinicMembership.Role.OWNER,
    )
    StaffAccount.objects.create(user=user, role=StaffAccount.Role.SUPERADMIN)
    return clinic


def test_login_success_returns_tokens_and_memberships(client, django_user_model):
    user = _make_user(django_user_model)
    clinic = _seed_membership(user)

    payload = {"email": user.email, "password": "Admin!234"}
    response = client.post(
        "/auth/login",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["user"]["email"] == user.email
    assert data["hq_role"] == StaffAccount.Role.SUPERADMIN
    assert data["clinics"] == [{"slug": clinic.slug, "role": ClinicMembership.Role.OWNER}]
    assert data["access"]
    assert data["refresh"]
    assert AuditLog.objects.filter(
        actor_user=user, action="LOGIN_SUCCESS", scope=AuditLog.Scope.AUTH
    ).exists()


def test_login_failure_records_audit_log(client, django_user_model):
    user = _make_user(django_user_model)
    _seed_membership(user)

    payload = {"email": user.email, "password": "wrong"}
    response = client.post(
        "/auth/login",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 401
    body = response.json()
    assert body == {"ok": False, "error": "INVALID_CREDENTIALS"}
    assert AuditLog.objects.filter(
        action="LOGIN_FAILURE", scope=AuditLog.Scope.AUTH, actor_user=user
    ).exists()


def test_auth_me_requires_token(client, django_user_model):
    user = _make_user(django_user_model)
    _seed_membership(user)

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    response = client.get(
        "/auth/me",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["user"]["email"] == user.email
    assert body["data"]["clinics"]
    assert body["data"]["hq_role"] == StaffAccount.Role.SUPERADMIN

    unauthorized = client.get("/auth/me")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["ok"] is False
