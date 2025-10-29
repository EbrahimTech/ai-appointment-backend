import json

import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ClinicMembership
from apps.channels.models import HSMTemplate, HSMTemplateStatus
from apps.clinics.models import Clinic
from apps.templates.models import MessageTemplate, TemplateCategory

pytestmark = pytest.mark.django_db


def _create_clinic(slug: str = "demo-clinic") -> Clinic:
    return Clinic.objects.create(slug=slug, name="Demo Dental", tz="UTC", default_lang="en")


def _make_user(email: str, role: ClinicMembership.Role, clinic: Clinic) -> User:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Agent",
        last_name="User",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _create_template(
    clinic: Clinic,
    *,
    code: str,
    language: str,
    body: str,
    variables=None,
    metadata=None,
    is_active: bool = True,
):
    variables = variables or []
    metadata = metadata or {}
    return MessageTemplate.objects.create(
        clinic=clinic,
        code=code,
        language=language,
        category=TemplateCategory.WHATSAPP,
        body=body,
        variables=variables,
        provider_template_id=f"{code}_{language}",
        metadata=metadata,
        is_active=is_active,
    )


def test_template_list_filters_by_lang_and_query(client):
    clinic = _create_clinic("templates")
    user = _make_user("viewer@example.com", ClinicMembership.Role.VIEWER, clinic)

    _create_template(
        clinic,
        code="greet",
        language="en",
        body="Hello {{name}}",
        variables=["name"],
        metadata={"hsm_name": "greet"},
    )
    _create_template(
        clinic,
        code="greet",
        language="ar",
        body="مرحبا {{name}}",
        variables=["name"],
        metadata={"hsm_name": "greet"},
    )
    HSMTemplate.objects.create(
        clinic=clinic,
        name="greet",
        language="en",
        body="Hello {{name}}",
        variables=["name"],
        status=HSMTemplateStatus.APPROVED,
        provider_template_id="greet_en_provider",
    )

    response = client.get(
        f"/clinic/{clinic.slug}/templates",
        {"lang": "en"},
        **_auth_headers(user),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item == {
        "key": "greet",
        "lang": "en",
        "channel": "whatsapp",
        "hsm": True,
        "variables": ["name"],
        "enabled": True,
    }

    response_q = client.get(
        f"/clinic/{clinic.slug}/templates",
        {"q": "مرحبا"},
        **_auth_headers(user),
    )
    assert response_q.status_code == 200
    items = response_q.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["lang"] == "ar"


def test_template_preview_lint_failed(client):
    clinic = _create_clinic("preview-fail")
    user = _make_user("staff@example.com", ClinicMembership.Role.STAFF, clinic)
    _create_template(
        clinic,
        code="slot_offer",
        language="en",
        body="Slots {{slot1}} or {{slot2}}",
        variables=["slot1", "slot2"],
    )

    response = client.post(
        f"/clinic/{clinic.slug}/templates/preview",
        data=json.dumps({"template_key": "slot_offer", "variables": {"slot1": "9am"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "LINT_FAILED"}


def test_template_preview_viewer_forbidden(client):
    clinic = _create_clinic("preview-forbidden")
    user = _make_user("viewer@example.com", ClinicMembership.Role.VIEWER, clinic)
    _create_template(
        clinic,
        code="greet",
        language="en",
        body="Hi {{name}}",
        variables=["name"],
    )

    response = client.post(
        f"/clinic/{clinic.slug}/templates/preview",
        data=json.dumps({"template_key": "greet", "variables": {"name": "Omar"}}),
        content_type="application/json",
        **_auth_headers(user),
    )
    assert response.status_code == 403
    assert response.json() == {"ok": False, "error": "FORBIDDEN"}
