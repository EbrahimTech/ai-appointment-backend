# Generated manually to increase language field max_length

from django.db import migrations, models
from apps.clinics.models import LanguageChoices


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patient',
            name='language',
            field=models.CharField(
                max_length=10,
                choices=LanguageChoices.choices,
                default=LanguageChoices.ENGLISH
            ),
        ),
    ]

