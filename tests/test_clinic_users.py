import json

import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, ClinicMembership
from apps.clinics.models import Clinic

pytestmark = pytest.mark.django_db


def _create_clinic(slug="membership-clinic"):
    return Clinic.objects.create(slug=slug, name="Membership Clinic", tz="UTC", default_lang="en")


def _create_user(email: str, clinic: Clinic, role: ClinicMembership.Role) -> User:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Owner" if role == ClinicMembership.Role.OWNER else "Member",
        last_name="User",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _post(client, path, payload, user):
    return client.post(path, data=json.dumps(payload), content_type="application/json", **_auth_headers(user))


def _put(client, path, payload, user):
    return client.put(path, data=json.dumps(payload), content_type="application/json", **_auth_headers(user))


def _delete(client, path, user):
    return client.delete(path, **_auth_headers(user))


def test_list_users_owner(client, django_user_model):
    clinic = _create_clinic("list-clinic")
    owner = _create_user("owner@example.com", clinic, ClinicMembership.Role.OWNER)
    staff = _create_user("staff@example.com", clinic, ClinicMembership.Role.STAFF)

    response = client.get(f"/clinic/{clinic.slug}/users", **_auth_headers(owner))
    assert response.status_code == 200
    data = response.json()["data"]["items"]
    assert len(data) == 2
    entry = next(item for item in data if item["email"] == staff.email)
    assert entry["role"] == ClinicMembership.Role.STAFF
    assert entry["name"]


def test_list_users_forbidden_for_staff(client, django_user_model):
    clinic = _create_clinic("forbidden-list")
    owner = _create_user("owner2@example.com", clinic, ClinicMembership.Role.OWNER)
    staff = _create_user("staff2@example.com", clinic, ClinicMembership.Role.STAFF)

    response = client.get(f"/clinic/{clinic.slug}/users", **_auth_headers(staff))
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}


def test_invite_creates_membership(client, django_user_model):
    clinic = _create_clinic("invite-clinic")
    owner = _create_user("owner3@example.com", clinic, ClinicMembership.Role.OWNER)

    resp = _post(
        client,
        f"/clinic/{clinic.slug}/users",
        {"email": "new-member@example.com", "role": "STAFF"},
        owner,
    )
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["invited"] is True
    membership = ClinicMembership.objects.get(id=payload["id"])
    assert membership.role == ClinicMembership.Role.STAFF
    assert AuditLog.objects.filter(action="USER_INVITE", clinic=clinic, meta__target_email="new-member@example.com").exists()


def test_invite_duplicate_idempotent(client, django_user_model):
    clinic = _create_clinic("duplicate-invite")
    owner = _create_user("owner4@example.com", clinic, ClinicMembership.Role.OWNER)

    first = _post(client, f"/clinic/{clinic.slug}/users", {"email": "dup@example.com", "role": "VIEWER"}, owner)
    assert first.status_code == 200

    second = _post(client, f"/clinic/{clinic.slug}/users", {"email": "dup@example.com", "role": "VIEWER"}, owner)
    assert second.status_code == 200
    assert second.json()["data"]["invited"] is False
    assert ClinicMembership.objects.filter(clinic=clinic, user__email="dup@example.com").count() == 1


def test_invite_invalid_role(client, django_user_model):
    clinic = _create_clinic("invalid-role")
    owner = _create_user("owner5@example.com", clinic, ClinicMembership.Role.OWNER)

    resp = _post(client, f"/clinic/{clinic.slug}/users", {"email": "bad@example.com", "role": "INVALID"}, owner)
    assert resp.status_code == 400
    assert resp.json() == {"ok": False, "error": "INVALID_ROLE"}


def test_invite_forbidden_for_staff(client, django_user_model):
    clinic = _create_clinic("staff-invite")
    owner = _create_user("owner6@example.com", clinic, ClinicMembership.Role.OWNER)
    staff = _create_user("staff3@example.com", clinic, ClinicMembership.Role.STAFF)

    resp = _post(client, f"/clinic/{clinic.slug}/users", {"email": "friend@example.com", "role": "STAFF"}, staff)
    assert resp.status_code == 403
    assert resp.json() == {"ok": False, "error": "FORBIDDEN"}


def test_update_role_success(client, django_user_model):
    clinic = _create_clinic("update-role")
    owner = _create_user("owner7@example.com", clinic, ClinicMembership.Role.OWNER)
    member = _create_user("member@example.com", clinic, ClinicMembership.Role.STAFF)
    membership = ClinicMembership.objects.get(clinic=clinic, user=member)

    resp = _put(client, f"/clinic/{clinic.slug}/users/{membership.id}", {"role": "ADMIN"}, owner)
    assert resp.status_code == 200
    membership.refresh_from_db()
    assert membership.role == ClinicMembership.Role.ADMIN
    assert AuditLog.objects.filter(action="USER_ROLE_UPDATE", clinic=clinic, meta__target_email=member.email).exists()


def test_update_invalid_role(client, django_user_model):
    clinic = _create_clinic("update-invalid")
    owner = _create_user("owner8@example.com", clinic, ClinicMembership.Role.OWNER)
    member = _create_user("member2@example.com", clinic, ClinicMembership.Role.STAFF)
    membership = ClinicMembership.objects.get(clinic=clinic, user=member)

    resp = _put(client, f"/clinic/{clinic.slug}/users/{membership.id}", {"role": "INVALID"}, owner)
    assert resp.status_code == 400
    assert resp.json() == {"ok": False, "error": "INVALID_ROLE"}


def test_update_forbidden_for_staff(client, django_user_model):
    clinic = _create_clinic("update-forbidden")
    owner = _create_user("owner9@example.com", clinic, ClinicMembership.Role.OWNER)
    staff = _create_user("staff4@example.com", clinic, ClinicMembership.Role.STAFF)
    target = _create_user("target@example.com", clinic, ClinicMembership.Role.VIEWER)
    membership = ClinicMembership.objects.get(clinic=clinic, user=target)

    resp = _put(client, f"/clinic/{clinic.slug}/users/{membership.id}", {"role": "STAFF"}, staff)
    assert resp.status_code == 403
    assert resp.json() == {"ok": False, "error": "FORBIDDEN"}


def test_delete_membership(client, django_user_model):
    clinic = _create_clinic("delete-member")
    owner = _create_user("owner10@example.com", clinic, ClinicMembership.Role.OWNER)
    member = _create_user("remove@example.com", clinic, ClinicMembership.Role.VIEWER)
    membership = ClinicMembership.objects.get(clinic=clinic, user=member)

    resp = _delete(client, f"/clinic/{clinic.slug}/users/{membership.id}", owner)
    assert resp.status_code == 200
    assert ClinicMembership.objects.filter(id=membership.id).exists() is False
    assert AuditLog.objects.filter(action="USER_REMOVE", clinic=clinic, meta__target_email=member.email).exists()


def test_delete_forbidden_for_staff(client, django_user_model):
    clinic = _create_clinic("delete-forbidden")
    owner = _create_user("owner11@example.com", clinic, ClinicMembership.Role.OWNER)
    staff = _create_user("staff5@example.com", clinic, ClinicMembership.Role.STAFF)
    member = _create_user("viewer2@example.com", clinic, ClinicMembership.Role.VIEWER)
    membership = ClinicMembership.objects.get(clinic=clinic, user=member)

    resp = _delete(client, f"/clinic/{clinic.slug}/users/{membership.id}", staff)
    assert resp.status_code == 403
    assert resp.json() == {"ok": False, "error": "FORBIDDEN"}
