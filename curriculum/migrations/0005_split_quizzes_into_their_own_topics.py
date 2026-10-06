"""Give every existing quiz a topic of its own.

Quizzes were generated as part of the topic they belong to, which made a topic two
things at once. Each one now becomes its own item, sitting immediately after the
lesson it tests, so the questions already generated are kept rather than regenerated.
"""

from django.db import migrations

# Positions are unique per chapter, so inserting between existing ones means first
# moving everything out of the way. Renumbering in place collides with the rows not
# yet renumbered.
PARKING = 10_000


def split(apps, schema_editor):
    Topic = apps.get_model("curriculum", "Topic")
    Quiz = apps.get_model("curriculum", "Quiz")

    # .order_by() clears Topic.Meta.ordering first. Without it Django adds `position`
    # to the SELECT so it can ORDER BY it, DISTINCT then applies to (chapter_id,
    # position), and every chapter comes back once per topic it contains — which runs
    # this whole function over the same chapter seven or eight times.
    chapter_ids = list(
        Topic.objects.order_by().values_list("chapter_id", flat=True).distinct()
    )
    for chapter_id in chapter_ids:
        topics = list(Topic.objects.filter(chapter_id=chapter_id).order_by("position"))
        if not topics:
            continue

        # Only lessons are split; a quiz topic has nothing to split off.
        topics = [topic for topic in topics if topic.kind != "quiz"]

        # Park them somewhere nothing else occupies, keeping their order.
        for offset, topic in enumerate(topics, start=1):
            Topic.objects.filter(pk=topic.pk).update(position=PARKING + offset)

        position = 0
        for topic in topics:
            position += 1
            Topic.objects.filter(pk=topic.pk).update(position=position)

            quiz = Quiz.objects.filter(topic_id=topic.pk).first()
            if quiz is None:
                continue

            position += 1
            quiz_topic = Topic.objects.create(
                chapter_id=chapter_id,
                position=position,
                kind="quiz",
                title=topic.title,
                summary=f"Check what you took from {topic.title}.",
                key_points=topic.key_points,
                page_start=topic.page_start,
                page_end=topic.page_end,
                status=topic.status,
            )
            Quiz.objects.filter(pk=quiz.pk).update(topic_id=quiz_topic.pk)


def rejoin(apps, schema_editor):
    """Put each quiz back on the lesson before it and drop the quiz topics."""
    Topic = apps.get_model("curriculum", "Topic")
    Quiz = apps.get_model("curriculum", "Quiz")

    for quiz_topic in list(Topic.objects.filter(kind="quiz").order_by("position")):
        lesson = (
            Topic.objects.filter(
                chapter_id=quiz_topic.chapter_id,
                kind="lesson",
                position__lt=quiz_topic.position,
            )
            .order_by("-position")
            .first()
        )
        quiz = Quiz.objects.filter(topic_id=quiz_topic.pk).first()
        if quiz is not None and lesson is not None:
            Quiz.objects.filter(pk=quiz.pk).update(topic_id=lesson.pk)
        quiz_topic.delete()


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0004_topic_kind")]
    operations = [migrations.RunPython(split, rejoin)]
