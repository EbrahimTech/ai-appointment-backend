from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="google_last_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="google_retry_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="appointment",
            name="sync_state",
            field=models.CharField(
                choices=[("ok", "OK"), ("tentative", "Tentative"), ("failed", "Failed")],
                default="ok",
                max_length=16,
            ),
        ),
    ]
