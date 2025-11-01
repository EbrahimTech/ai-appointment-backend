import json
import time
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Invitation, ClinicMembership, StaffAccount
from apps.clinics.models import Clinic

pytestmark = pytest.mark.django_db


def _create_hq_user(django_user_model, role=StaffAccount.Role.SUPERADMIN):
    user = django_user_model.objects.create_user(
        username=f"{role.lower()}@hq.example.com",
        email=f"{role.lower()}@hq.example.com",
        password="Admin!234",
        first_name="HQ",
        last_name="User",
        is_active=True,
    )
    StaffAccount.objects.create(user=user, role=role)
    return user


def _headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _post_json(client, path, payload, headers):
    client.defaults["REMOTE_ADDR"] = f"10.30.{int(time.time() * 1000) % 250}.{int(time.time() * 1000) % 250}"
    return client.post(path, data=json.dumps(payload), content_type="application/json", **headers)


def test_hq_create_tenant_invite(client, django_user_model):
    hq_user = _create_hq_user(django_user_model)
    payload = {
        "name": "New Clinic",
        "slug": "new-clinic",
        "default_lang": "en",
        "tz": "UTC",
        "owner_email": "owner@example.com",
        "owner_name": "Owner Person",
    }

    response = _post_json(client, "/hq/tenants", payload, _headers(hq_user))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["clinic"]["slug"] == payload["slug"]
    assert data["owner"]["email"] == payload["owner_email"]
    assert data["invite_token"]

    clinic = Clinic.objects.get(slug=payload["slug"])
    membership = ClinicMembership.objects.get(clinic=clinic, user__email=payload["owner_email"])
    assert membership.role == ClinicMembership.Role.OWNER
    invitation = Invitation.objects.get(clinic=clinic, user=membership.user)
    assert invitation.accepted_at is None


def test_hq_create_tenant_invite_idempotent(client, django_user_model):
    hq_user = _create_hq_user(django_user_model)
    payload = {
        "name": "Same Clinic",
        "slug": "same-clinic",
        "default_lang": "en",
        "tz": "UTC",
        "owner_email": "same-owner@example.com",
        "owner_name": "Same Owner",
    }

    resp1 = _post_json(client, "/hq/tenants", payload, _headers(hq_user))
    assert resp1.status_code == 200
    token1 = resp1.json()["data"]["invite_token"]

    resp2 = _post_json(client, "/hq/tenants", payload, _headers(hq_user))
    assert resp2.status_code == 200
    token2 = resp2.json()["data"]["invite_token"]

    assert token1 == token2
    invitation = Invitation.objects.get(clinic__slug=payload["slug"], user__email=payload["owner_email"])
    assert invitation.accepted_at is None


def test_accept_invite_success(client, django_user_model):
    hq_user = _create_hq_user(django_user_model)
    payload = {
        "name": "Accept Clinic",
        "slug": "accept-clinic",
        "default_lang": "en",
        "tz": "UTC",
        "owner_email": "accept-owner@example.com",
        "owner_name": "Accept Owner",
    }

    invite_resp = _post_json(client, "/hq/tenants", payload, _headers(hq_user))
    token = invite_resp.json()["data"]["invite_token"]

    accept_resp = client.post(
        "/auth/accept-invite",
        data=json.dumps({"token": token, "password": "Owner!234", "first_name": "Accept", "last_name": "Owner"}),
        content_type="application/json",
    )
    assert accept_resp.status_code == 200
    user = User.objects.get(email=payload["owner_email"])
    assert user.is_active is True
    assert user.check_password("Owner!234")
    invitation = Invitation.objects.get(clinic__slug=payload["slug"], user=user)
    assert invitation.accepted_at is not None


def test_accept_invite_expired(client, django_user_model):
    hq_user = _create_hq_user(django_user_model)
    payload = {
        "name": "Expired Clinic",
        "slug": "expired-clinic",
        "default_lang": "en",
        "tz": "UTC",
        "owner_email": "expired-owner@example.com",
        "owner_name": "Expired Owner",
    }

    invite_resp = _post_json(client, "/hq/tenants", payload, _headers(hq_user))
    token = invite_resp.json()["data"]["invite_token"]

    invitation = Invitation.objects.get(clinic__slug=payload["slug"], user__email=payload["owner_email"])
    invitation.expires_at = timezone.now() - timedelta(hours=1)
    invitation.save(update_fields=["expires_at"])

    resp = client.post(
        "/auth/accept-invite",
        data=json.dumps({"token": token, "password": "Owner!234"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "TOKEN_EXPIRED"


def test_hq_create_tenant_requires_privileged_role(client, django_user_model):
    support_user = _create_hq_user(django_user_model, role=StaffAccount.Role.SUPPORT)
    payload = {
        "name": "NoPe Clinic",
        "slug": "nope-clinic",
        "default_lang": "en",
        "tz": "UTC",
        "owner_email": "nope-owner@example.com",
        "owner_name": "Nope Owner",
    }

    resp = _post_json(client, "/hq/tenants", payload, _headers(support_user))
    assert resp.status_code == 403
