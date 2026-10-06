"""Put the quiz back on the topic it belongs to, and drop `kind`.

Splitting a topic into two items was the wrong fix for the right problem. A quiz did
need its own page — but that is a rendering decision, and it was made in the database,
where it left the thing a person calls a "topic" with no representation at all. There
were only items, and a lesson's relationship to its quiz was implied by them sitting
at adjacent positions.

A topic is the unit. It holds one lesson and one quiz, which are shown as separate
pages because they are different kinds of work, not because they are different rows.
"""

from django.db import migrations

PARKING = 10_000


def merge(apps, schema_editor):
    Topic = apps.get_model("curriculum", "Topic")
    Quiz = apps.get_model("curriculum", "Quiz")

    # .order_by() clears Topic.Meta.ordering: without it Django adds `position` to the
    # SELECT for the ORDER BY, DISTINCT applies to the pair, and every chapter comes
    # back once per topic it holds.
    chapter_ids = list(
        Topic.objects.order_by().values_list("chapter_id", flat=True).distinct()
    )

    for chapter_id in chapter_ids:
        topics = list(Topic.objects.filter(chapter_id=chapter_id).order_by("position"))

        for quiz_topic in [t for t in topics if t.kind == "quiz"]:
            lesson = (
                Topic.objects.filter(
                    chapter_id=chapter_id, kind="lesson", position__lt=quiz_topic.position
                )
                .order_by("-position")
                .first()
            )
            quiz = Quiz.objects.filter(topic_id=quiz_topic.pk).first()
            if quiz is not None and lesson is not None:
                Quiz.objects.filter(topic_id=lesson.pk).delete()
                Quiz.objects.filter(pk=quiz.pk).update(topic_id=lesson.pk)
            quiz_topic.delete()

        # Close the gaps the removed items left. Park first: positions are unique per
        # chapter, so renumbering in place collides with rows not yet renumbered.
        remaining = list(Topic.objects.filter(chapter_id=chapter_id).order_by("position"))
        for offset, topic in enumerate(remaining, start=1):
            Topic.objects.filter(pk=topic.pk).update(position=PARKING + offset)
        for position, topic in enumerate(remaining, start=1):
            Topic.objects.filter(pk=topic.pk).update(position=position)


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0006_clean_quiz_titles")]

    # Data only. Postgres refuses to ALTER a table in the same transaction as data
    # changes that leave constraint triggers pending, so dropping the column is its
    # own migration.
    operations = [migrations.RunPython(merge, migrations.RunPython.noop)]
