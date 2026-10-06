"""Turn the AI service's JSON into rows.

Kept apart from the Celery tasks so the mapping can be tested without a broker,
and so there is one place to look when the AI schema changes.
"""

from typing import Any

from curriculum.models import (
    Chapter,
    Exercise,
    ExerciseStep,
    Lesson,
    Question,
    Quiz,
    Syllabus,
    Topic,
)
from documents.models import Document


class WouldDestroyContent(Exception):
    """Refused to overwrite generated content that nobody asked to replace."""


def save_structure(
    document: Document, data: dict[str, Any], language: str, *, replace: bool = False
) -> Syllabus:
    """Create the syllabus and its chapters from the document's own structure.

    No model produced any of this: the chapters, their titles and their page ranges
    come from the PDF's bookmarks. Topics are not created here — each chapter's are
    worked out when that chapter is reached.
    """
    existing = Syllabus.objects.filter(document=document)
    if existing.exists() and not replace:
        raise WouldDestroyContent(
            f"Document {document.pk} already has a syllabus. Replacing it would "
            f"delete every chapter, topic, lesson and checkpoint under it. Pass "
            f"replace=True if that is genuinely what you want."
        )
    existing.delete()

    chapters = data["chapters"]
    syllabus = Syllabus.objects.create(
        document=document,
        title=document.title,
        subject="",
        description=f"{len(chapters)} chapters over {data['page_count']} pages.",
        language=language,
    )

    for chapter in chapters:
        Chapter.objects.create(
            syllabus=syllabus,
            number=chapter["number"],
            title=chapter["title"],
            summary="",
            page_start=chapter["page_start"],
            page_end=chapter["page_end"],
            headings=chapter["headings"],
        )

    return syllabus


def save_topics(
    chapter: Chapter, topics: list[dict[str, Any]], *, replace: bool = False
) -> list[Topic]:
    """Write this chapter's topics. Refuses to overwrite topics that already exist."""
    existing = Topic.objects.filter(chapter=chapter)
    if existing.exists() and not replace:
        raise WouldDestroyContent(
            f"Chapter {chapter.number} already has {existing.count()} topics, with "
            f"their lessons and exercises. Pass replace=True to discard them."
        )
    existing.delete()

    # Each returned topic becomes two items: the lesson, and the quiz that tests it.
    # Created together and interleaved, so positions are settled up front rather than
    # inserted into later — which would mean renumbering everything after them.
    lessons: list[Topic] = []
    position = 0
    for topic in topics:
        position += 1
        lessons.append(
            Topic.objects.create(
                chapter=chapter,
                position=position,
                kind=Topic.Kind.LESSON,
                title=topic["title"],
                summary=topic["summary"],
                key_points=topic["key_points"],
                page_start=topic["page_start"],
                page_end=topic["page_end"],
            )
        )
        position += 1
        Topic.objects.create(
            chapter=chapter,
            position=position,
            kind=Topic.Kind.QUIZ,
            title=topic["title"],
            summary=f"Check what you took from {topic['title']}.",
            key_points=topic["key_points"],
            page_start=topic["page_start"],
            page_end=topic["page_end"],
        )
    return lessons


def save_topic_content(topic: Topic, content: dict[str, Any], *, replace: bool = False) -> None:
    """Write this topic's lesson, quiz and exercises.

    Refuses to overwrite a topic that already has them — a finished topic is the
    thing a learner may already have worked through, and its checkpoints carry their
    completion records.
    """
    already = Lesson.objects.filter(topic=topic).exists() or Exercise.objects.filter(
        topic=topic
    ).exists()
    if already and not replace:
        raise WouldDestroyContent(
            f"Topic {topic.pk} ({topic.title!r}) already has content. Pass "
            f"replace=True to discard it."
        )

    Lesson.objects.filter(topic=topic).delete()
    Quiz.objects.filter(topic=topic).delete()
    Exercise.objects.filter(topic=topic).delete()

    lesson = content["lesson"]
    Lesson.objects.create(
        topic=topic, title=lesson["title"], body_markdown=lesson["body_markdown"]
    )

    # The quiz belongs to the quiz item that follows this lesson, not to the lesson.
    quiz_topic = (
        Topic.objects.filter(
            chapter=topic.chapter, kind=Topic.Kind.QUIZ, position=topic.position + 1
        ).first()
        or topic
    )
    Quiz.objects.filter(topic=quiz_topic).delete()
    quiz = Quiz.objects.create(topic=quiz_topic)
    for position, question in enumerate(content["quiz"]["questions"], start=1):
        Question.objects.create(
            quiz=quiz,
            position=position,
            prompt=question["prompt"],
            choices=question["choices"],
            correct_index=question["correct_index"],
            explanation=question["explanation"],
        )

    if quiz_topic is not topic:
        quiz_topic.status = Topic.Status.READY
        quiz_topic.error = ""
        quiz_topic.save(update_fields=["status", "error"])

    for position, exercise_data in enumerate(content["exercises"], start=1):
        exercise = Exercise.objects.create(
            topic=topic,
            position=position,
            title=exercise_data["title"],
            scenario_markdown=exercise_data["scenario_markdown"],
            language=exercise_data["language"],
        )
        for number, step in enumerate(exercise_data["steps"], start=1):
            ExerciseStep.objects.create(
                exercise=exercise,
                number=number,
                instruction_markdown=step["instruction_markdown"],
                explanation_markdown=step["explanation_markdown"],
                starter_code=step["starter_code"],
                expected_code=step["expected_code"],
                hint=step.get("hint") or "",
            )
