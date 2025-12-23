from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dialog", "0002_dialogturnlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialogturnlog",
            name="slots",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="dialogturnlog",
            name="missing_slots",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
