from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def forwards_role_to_user_type(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    mapping = {
        "super_admin": "admin",
        "college_admin": "admin",
        "trainer": "trainer",
        "finance_officer": "finance",
        "student": "student",
    }
    for u in User.objects.all():
        old = getattr(u, "role", None)
        if old:
            u.user_type = mapping.get(old, "student")
            u.save(update_fields=["user_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="user_type",
            field=models.CharField(
                choices=[
                    ("admin", "Administrator"),
                    ("trainer", "Trainer"),
                    ("finance", "Finance"),
                    ("student", "Student"),
                ],
                db_index=True,
                default="student",
                max_length=32,
            ),
        ),
        migrations.RunPython(forwards_role_to_user_type, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="user",
            name="role",
        ),
        migrations.AlterField(
            model_name="trainerprofile",
            name="user",
            field=models.OneToOneField(
                limit_choices_to={"user_type": "trainer"},
                on_delete=django.db.models.deletion.CASCADE,
                related_name="trainer_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
