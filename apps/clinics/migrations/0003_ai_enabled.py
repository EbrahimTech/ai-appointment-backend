from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinics", "0002_increase_language_field_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinic",
            name="ai_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
