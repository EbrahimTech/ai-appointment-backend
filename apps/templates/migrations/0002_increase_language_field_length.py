# Generated manually to increase language field max_length

from django.db import migrations, models
import apps.clinics.models


class Migration(migrations.Migration):

    dependencies = [
        ('templates', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='messagetemplate',
            name='language',
            field=models.CharField(
                choices=apps.clinics.models.LanguageChoices.choices,
                default='en',
                max_length=10
            ),
        ),
    ]

