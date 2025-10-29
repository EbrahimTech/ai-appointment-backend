"""Management command to load initial clinic, template, and KB seed data."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.clinics.models import Clinic, ClinicService, LanguageChoices, ServiceHours
from apps.accounts.models import AuditLog, ClinicMembership, StaffAccount
from apps.kb.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndex
from apps.channels.models import HSMTemplate, HSMTemplateStatus
from apps.templates.models import MessageTemplate, TemplateCategory


class Command(BaseCommand):
    help = "Import clinic, template, and knowledge base seeds into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clinic-file",
            default="seeds/clinic_seed.json",
            help="Path to clinic seed JSON file.",
        )
        parser.add_argument(
            "--template-file",
            default="seeds/templates_seed.json",
            help="Path to template seed JSON file.",
        )
        parser.add_argument(
            "--kb-ar-file",
            default="seeds/kb_ar.yaml",
            help="Path to Arabic knowledge base YAML file.",
        )
        parser.add_argument(
            "--kb-en-file",
            default="seeds/kb_en.yaml",
            help="Path to English knowledge base YAML file.",
        )

    def handle(self, *args, **options):
        clinic_path = Path(options["clinic_file"])
        template_path = Path(options["template_file"])
        kb_ar_path = Path(options["kb_ar_file"])
        kb_en_path = Path(options["kb_en_file"])

        if not clinic_path.exists():
            raise CommandError(f"Clinic seed file not found: {clinic_path}")
        if not template_path.exists():
            raise CommandError(f"Template seed file not found: {template_path}")
        if not kb_ar_path.exists():
            raise CommandError(f"Arabic KB seed file not found: {kb_ar_path}")
        if not kb_en_path.exists():
            raise CommandError(f"English KB seed file not found: {kb_en_path}")

        with transaction.atomic():
            clinic_data = self._load_json(clinic_path)
            template_data = self._load_json(template_path)
            kb_documents = self._load_kb_docs([kb_ar_path, kb_en_path])

            clinics = self._seed_clinics(clinic_data.get("clinics", []))
            self._seed_templates(template_data.get("templates", []), clinics)
            self._seed_knowledge_base(kb_documents, clinics)
            self._seed_auth(clinics)

        self.stdout.write(self.style.SUCCESS("Seed data imported successfully."))

    # --------------------------------------------------------------------- utils
    def _load_json(self, path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _load_kb_docs(self, files: Iterable[Path]) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        for file_path in files:
            with file_path.open("r", encoding="utf-8") as fh:
                payload = yaml.safe_load(fh) or {}
                documents.extend(payload.get("documents", []))
        return documents

    def _seed_clinics(self, clinic_payloads: List[Dict[str, Any]]) -> Dict[str, Clinic]:
        clinics: Dict[str, Clinic] = {}
        for payload in clinic_payloads:
            clinic, _ = Clinic.objects.update_or_create(
                slug=payload["slug"],
                defaults={
                    "name": payload["name"],
                    "tz": payload.get("tz") or payload.get("timezone", "UTC"),
                    "default_lang": payload.get("default_lang", "en"),
                    "phone_number": payload.get("phone_number", ""),
                    "whatsapp_number": payload.get("whatsapp_number", ""),
                    "address": payload.get("address", ""),
                },
            )
            clinics[clinic.slug] = clinic
            self._seed_services(clinic, payload.get("services", []))
            self._seed_service_hours(clinic, payload.get("service_hours", []))
        return clinics

    def _seed_services(self, clinic: Clinic, services: List[Dict[str, Any]]) -> None:
        for service in services:
            ClinicService.objects.update_or_create(
                clinic=clinic,
                code=service["code"],
                language=service.get("language", LanguageChoices.ENGLISH),
                defaults={
                    "name": service.get("name", service["code"]),
                    "description": service.get("description", ""),
                    "duration_minutes": service.get("duration_minutes", 30),
                    "is_active": service.get("is_active", True),
                },
            )

    def _seed_service_hours(self, clinic: Clinic, hours_payloads: List[Dict[str, Any]]) -> None:
        for hours in hours_payloads:
            service = clinic.services.filter(code=hours["service_code"]).first()
            if not service:
                self.stderr.write(
                    self.style.WARNING(
                        f"Service with code {hours['service_code']} not found for clinic {clinic.slug}"
                    )
                )
                continue

            start_time = datetime.strptime(hours["start"], "%H:%M").time()
            end_time = datetime.strptime(hours["end"], "%H:%M").time()

            ServiceHours.objects.update_or_create(
                clinic=clinic,
                service=service,
                weekday=hours["weekday"],
                start_time=start_time,
                defaults={"end_time": end_time},
            )

    def _seed_templates(
        self,
        templates: List[Dict[str, Any]],
        clinics: Dict[str, Clinic],
    ) -> None:
        for payload in templates:
            clinic_slug = payload["clinic_slug"]
            clinic = clinics.get(clinic_slug)
            if not clinic:
                self.stderr.write(
                    self.style.WARNING(f"Clinic {clinic_slug} not found for template {payload['code']}")
                )
                continue

            MessageTemplate.objects.update_or_create(
                clinic=clinic,
                code=payload["code"],
                language=payload.get("language", LanguageChoices.ENGLISH),
                defaults={
                    "category": payload.get("category", TemplateCategory.WHATSAPP),
                    "subject": payload.get("subject", ""),
                    "body": payload.get("body", ""),
                    "variables": payload.get("variables", []),
                    "provider_template_id": payload.get("provider_template_id", ""),
                    "is_active": payload.get("is_active", True),
                    "metadata": payload.get("metadata", {}),
                },
            )

            HSMTemplate.objects.update_or_create(
                clinic=clinic,
                name=payload.get("hsm_name", payload["code"]),
                language=payload.get("language", LanguageChoices.ENGLISH),
                defaults={
                    "body": payload.get("body", ""),
                    "variables": payload.get("variables", []),
                    "status": payload.get("status", HSMTemplateStatus.APPROVED),
                    "provider_template_id": payload.get("provider_template_id", ""),
                },
            )

    def _seed_knowledge_base(
        self,
        documents: List[Dict[str, Any]],
        clinics: Dict[str, Clinic],
    ) -> None:
        for clinic in clinics.values():
            index, _ = KnowledgeIndex.objects.update_or_create(
                clinic=clinic,
                name="default",
                defaults={"dimensions": 1536, "retriever_config": {"top_k": 4}},
            )

            linked_docs = []
            for payload in documents:
                language = payload.get("language", LanguageChoices.ENGLISH)
                if language not in (LanguageChoices.ENGLISH, LanguageChoices.ARABIC):
                    continue

                doc, _ = KnowledgeDocument.objects.update_or_create(
                    clinic=clinic,
                    title=payload["title"],
                    language=language,
                    defaults={
                        "source": payload.get("source", "seed"),
                        "body": payload.get("body", ""),
                        "metadata": payload.get("metadata", {}),
                    },
                )
                self._seed_chunks(doc)
                linked_docs.append(doc)

            if linked_docs:
                index.documents.set(linked_docs)

    def _seed_chunks(self, document: KnowledgeDocument) -> None:
        KnowledgeChunk.objects.filter(document=document).delete()
        paragraphs = [para.strip() for para in document.body.split("\n\n") if para.strip()]
        if not paragraphs:
            paragraphs = [document.body]
        for idx, content in enumerate(paragraphs):
            KnowledgeChunk.objects.create(
                document=document,
                chunk_index=idx,
                content=content,
                metadata={"seed": True},
                language=document.language,
                tags=document.metadata.get("tags", []),
            )

    def _seed_auth(self, clinics: Dict[str, Clinic]) -> None:
        clinic = clinics.get("demo-dental")
        if not clinic:
            clinic, _ = Clinic.objects.update_or_create(
                slug="demo-dental",
                defaults={
                    "name": "Demo Dental",
                    "tz": "Europe/Istanbul",
                    "default_lang": "ar",
                },
            )

        user, created = User.objects.get_or_create(
            email="admin@example.com",
            defaults={
                "username": "admin@example.com",
                "first_name": "Admin",
                "last_name": "User",
                "is_staff": True,
                "is_superuser": False,
            },
        )
        if created or not user.check_password("Admin!234"):
            user.set_password("Admin!234")
            user.save()

        ClinicMembership.objects.update_or_create(
            user=user,
            clinic=clinic,
            defaults={"role": ClinicMembership.Role.OWNER},
        )
        StaffAccount.objects.update_or_create(
            user=user, defaults={"role": StaffAccount.Role.SUPERADMIN}
        )
        AuditLog.objects.get_or_create(
            actor_user=user,
            action="seed.superadmin.created",
            scope=AuditLog.Scope.AUTH,
            defaults={"meta": {"email": user.email}},
        )

