from django.db import migrations, models


def migrate_roles(apps, schema_editor):
    StaffAccount = apps.get_model("accounts", "StaffAccount")
    StaffAccount.objects.filter(role__in=["SUPPORT", "SALES"]).update(role="OPS")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_rename_accounts_no_clinic__2fcf95_idx_accounts_no_clinic__a438a5_idx"),
    ]

    operations = [
        migrations.RunPython(migrate_roles, noop),
        migrations.AlterField(
            model_name="staffaccount",
            name="role",
            field=models.CharField(choices=[("SUPERADMIN", "Super Admin"), ("OPS", "Ops")], max_length=20),
        ),
    ]
