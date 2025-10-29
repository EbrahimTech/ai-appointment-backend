import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ClinicMembership
from apps.clinics.models import Clinic
from apps.kb.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndex

pytestmark = pytest.mark.django_db


def _make_clinic():
    return Clinic.objects.create(slug="demo", name="Demo", tz="UTC", default_lang="en")


def _make_user(django_user_model, clinic, email, role):
    user = django_user_model.objects.create_user(
        username=email,
        email=email,
        password="Admin!234",
        first_name="Admin",
        last_name="User",
        is_active=True,
    )
    ClinicMembership.objects.create(user=user, clinic=clinic, role=role)
    return user


def _auth_headers(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _post(client, path, data, user, content_type="application/json", remote="10.10.0.1"):
    client.defaults["REMOTE_ADDR"] = remote
    return client.post(path, data=data, content_type=content_type, **_auth_headers(user))


def test_upload_invalid_schema(client, django_user_model):
    clinic = _make_clinic()
    admin = _make_user(django_user_model, clinic, "owner@example.com", ClinicMembership.Role.OWNER)

    client.defaults["REMOTE_ADDR"] = "10.0.2.1"
    response = client.post(
        f"/clinic/{clinic.slug}/kb/upload",
        data={"file": SimpleUploadedFile("kb.yaml", b"not: [valid", content_type="application/x-yaml")},
        **_auth_headers(admin),
    )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "INVALID_SCHEMA"}

    bad_yaml = """
documents:
  - title: "No Tag"
    language: "en"
    body: "Missing tag field."
"""
    client.defaults["REMOTE_ADDR"] = "10.0.2.2"
    response = client.post(
        f"/clinic/{clinic.slug}/kb/upload",
        data={"file": SimpleUploadedFile("kb.yaml", bad_yaml.encode(), content_type="application/x-yaml")},
        **_auth_headers(admin),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_SCHEMA"


def test_upload_publish_and_preview(client, django_user_model, settings):
    clinic = _make_clinic()
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)

    yaml_payload = """
documents:
  - title: "Cleaning FAQ"
    lang: "en"
    tag: "faq"
    body: |
      Cleaning visits last 30 minutes.
      We recommend coming fasting for sedation cases.
  - title: "تنظيف"
    lang: "ar"
    tag: "service"
    body: |
      تنظيف الأسنان يستغرق ٣٠ دقيقة.
      يجب الحضور قبل الموعد بعشر دقائق.
"""
    client.defaults["REMOTE_ADDR"] = "10.0.2.3"
    upload_resp = client.post(
        f"/clinic/{clinic.slug}/kb/upload",
        data={"file": SimpleUploadedFile("kb.yaml", yaml_payload.encode(), content_type="application/x-yaml")},
        **_auth_headers(admin),
    )
    assert upload_resp.status_code == 200
    assert KnowledgeDocument.objects.filter(clinic=clinic).count() == 2

    publish_resp = _post(
        client,
        f"/clinic/{clinic.slug}/kb/publish",
        data=json.dumps({}),
        user=admin,
    )
    assert publish_resp.status_code == 200
    assert KnowledgeChunk.objects.filter(document__clinic=clinic).count() >= 2
    assert KnowledgeIndex.objects.filter(clinic=clinic).exists()

    preview_ar = _post(
        client,
        f"/clinic/{clinic.slug}/kb/preview",
        data=json.dumps({"q": "كم مدة تنظيف", "lang": "ar"}),
        user=admin,
    )
    assert preview_ar.status_code == 200
    payload = preview_ar.json()["data"]["chunks"]
    assert payload
    assert all(chunk["lang"] == "ar" for chunk in payload)

    preview_en = _post(
        client,
        f"/clinic/{clinic.slug}/kb/preview",
        data=json.dumps({"q": "How long cleaning", "lang": "en"}),
        user=admin,
    )
    chunks = preview_en.json()["data"]["chunks"]
    assert chunks
    assert chunks[0]["lang"] == "en"


def test_preview_token_cap(client, django_user_model, settings):
    settings.RAG_MAX_TOKENS = 5
    settings.RAG_CHARS_PER_TOKEN = 4

    clinic = _make_clinic()
    admin = _make_user(django_user_model, clinic, "admin@example.com", ClinicMembership.Role.ADMIN)

    document = KnowledgeDocument.objects.create(
        clinic=clinic,
        title="Long Doc",
        language="en",
        body="",
        metadata={"tag": "faq", "pending": False},
    )
    long_text = "Long text " * 200
    KnowledgeChunk.objects.create(
        document=document,
        chunk_index=0,
        content=long_text,
        language="en",
        tags=["faq"],
        metadata={"tag": "faq"},
    )

    response = _post(
        client,
        f"/clinic/{clinic.slug}/kb/preview",
        data=json.dumps({"q": "long", "lang": "en"}),
        user=admin,
    )
    assert response.status_code == 200
    chunks = response.json()["data"]["chunks"]
    assert chunks
    assert len(chunks) == 1
    assert len(chunks[0]["excerpt"]) <= settings.RAG_MAX_TOKENS * settings.RAG_CHARS_PER_TOKEN
