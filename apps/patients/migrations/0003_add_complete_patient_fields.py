# Generated manually to add complete patient fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0002_increase_language_field_length'),
    ]

    operations = [
        # Contact Information
        migrations.AddField(
            model_name='patient',
            name='alternative_phone',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='patient',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='patient',
            name='emergency_contact_phone',
            field=models.CharField(blank=True, max_length=32),
        ),
        
        # Personal Information
        migrations.AddField(
            model_name='patient',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='patient',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
                max_length=10
            ),
        ),
        
        # Address Information
        migrations.AddField(
            model_name='patient',
            name='city',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='patient',
            name='district',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='patient',
            name='address',
            field=models.TextField(blank=True),
        ),
        
        # Medical Information
        migrations.AddField(
            model_name='patient',
            name='allergies',
            field=models.TextField(blank=True, help_text='List of known allergies'),
        ),
        migrations.AddField(
            model_name='patient',
            name='chronic_diseases',
            field=models.TextField(blank=True, help_text='List of chronic diseases'),
        ),
        migrations.AddField(
            model_name='patient',
            name='current_medications',
            field=models.TextField(blank=True, help_text='Current medications'),
        ),
        migrations.AddField(
            model_name='patient',
            name='blood_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('A+', 'A+'), ('A-', 'A-'),
                    ('B+', 'B+'), ('B-', 'B-'),
                    ('AB+', 'AB+'), ('AB-', 'AB-'),
                    ('O+', 'O+'), ('O-', 'O-'),
                ],
                max_length=5
            ),
        ),
        
        # General Notes
        migrations.AddField(
            model_name='patient',
            name='notes',
            field=models.TextField(blank=True, help_text='General notes about the patient'),
        ),
        
        # Fix PatientNote related_name
        migrations.AlterField(
            model_name='patientnote',
            name='patient',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='patient_notes',
                to='patients.patient'
            ),
        ),
    ]

