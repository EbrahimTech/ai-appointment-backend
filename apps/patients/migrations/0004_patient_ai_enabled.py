from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0003_add_complete_patient_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="ai_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
