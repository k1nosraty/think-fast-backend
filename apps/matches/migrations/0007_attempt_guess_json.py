from django.db import migrations, models


def copy_guess_to_json(apps, schema_editor):
    attempt_model = apps.get_model("matches", "Attempt")
    for attempt in attempt_model.objects.only("id", "guess").iterator():
        attempt_model.objects.filter(pk=attempt.pk).update(guess_json=attempt.guess)


def copy_guess_to_text(apps, schema_editor):
    attempt_model = apps.get_model("matches", "Attempt")
    for attempt in attempt_model.objects.only("id", "guess_json").iterator():
        value = attempt.guess_json
        attempt_model.objects.filter(pk=attempt.pk).update(
            guess=value if isinstance(value, str) else ""
        )


class Migration(migrations.Migration):
    dependencies = [("matches", "0006_rematchproposal")]

    operations = [
        migrations.AddField(
            model_name="attempt",
            name="guess_json",
            field=models.JSONField(null=True),
        ),
        migrations.RunPython(copy_guess_to_json, copy_guess_to_text),
        migrations.AlterField(
            model_name="attempt",
            name="guess",
            field=models.CharField(default="", max_length=6),
        ),
        migrations.RemoveField(model_name="attempt", name="guess"),
        migrations.RenameField(model_name="attempt", old_name="guess_json", new_name="guess"),
        migrations.AlterField(model_name="attempt", name="guess", field=models.JSONField()),
    ]
