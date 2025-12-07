# Generated manually to increase language field max_length

from django.db import migrations, models
from apps.clinics.models import LanguageChoices


class Migration(migrations.Migration):

    dependencies = [
        ('kb', '0002_knowledgechunk_language_knowledgechunk_tags'),
    ]

    operations = [
        migrations.AlterField(
            model_name='knowledgedocument',
            name='language',
            field=models.CharField(
                max_length=10,
                choices=LanguageChoices.choices,
                default=LanguageChoices.ENGLISH
            ),
        ),
        migrations.AlterField(
            model_name='knowledgechunk',
            name='language',
            field=models.CharField(
                max_length=10,
                choices=LanguageChoices.choices,
                default=LanguageChoices.ENGLISH
            ),
        ),
    ]

