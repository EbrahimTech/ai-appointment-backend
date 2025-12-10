from django.db import migrations, models
import django.db.models.deletion
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0003_add_complete_patient_fields"),
        ("conversations", "0002_increase_language_field_length"),
        ("clinics", "0002_increase_language_field_length"),
        ("accounts", "0002_supportsession"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("type", models.CharField(choices=[("handoff", "Handoff")], default="handoff", max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[("new", "New"), ("read", "Read")], db_index=True, default="new", max_length=10
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True)),
                ("patient_name", models.CharField(blank=True, max_length=255)),
                ("patient_phone", models.CharField(blank=True, max_length=32)),
                (
                    "clinic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="clinics.clinic",
                    ),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notifications",
                        to="conversations.conversation",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notifications",
                        to="patients.patient",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["clinic", "status"], name="accounts_no_clinic__2fcf95_idx"),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("conversation__isnull", False)),
                fields=("conversation", "type"),
                name="unique_notification_per_conversation_type",
            ),
        ),
    ]
