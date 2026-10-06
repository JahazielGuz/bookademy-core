"""Drop the "— quiz" suffix from quiz topic titles.

The suffix was carrying information the title should not have to: a quiz is marked as
one by its `kind`, and the interface can say so in its own voice. Repeating it in the
title gives every chapter a column of near-duplicate strings.
"""

from django.db import migrations

SUFFIX = " — quiz"


def strip(apps, schema_editor):
    Topic = apps.get_model("curriculum", "Topic")
    for topic in Topic.objects.filter(kind="quiz", title__endswith=SUFFIX):
        Topic.objects.filter(pk=topic.pk).update(title=topic.title[: -len(SUFFIX)])


def restore(apps, schema_editor):
    Topic = apps.get_model("curriculum", "Topic")
    for topic in Topic.objects.filter(kind="quiz").exclude(title__endswith=SUFFIX):
        Topic.objects.filter(pk=topic.pk).update(title=f"{topic.title}{SUFFIX}")


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0005_split_quizzes_into_their_own_topics")]
    operations = [migrations.RunPython(strip, restore)]
