# Generated manually to increase access_token and refresh_token max_length

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0002_hsmtemplate_remove_outboxmessage_template_code_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='channelaccount',
            name='access_token',
            field=models.CharField(max_length=1000),
        ),
        migrations.AlterField(
            model_name='channelaccount',
            name='refresh_token',
            field=models.CharField(blank=True, max_length=1000),
        ),
    ]

