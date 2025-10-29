from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calendars", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="googlecredential",
            name="last_free_busy_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="googlecredential",
            name="last_error_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="googlecredential",
            name="last_error",
            field=models.TextField(blank=True),
        ),
    ]
