# Generated manually to increase language field max_length

from django.db import migrations, models
from apps.clinics.models import LanguageChoices


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conversationmessage',
            name='language',
            field=models.CharField(
                max_length=10,
                choices=LanguageChoices.choices,
                default=LanguageChoices.ENGLISH
            ),
        ),
    ]


