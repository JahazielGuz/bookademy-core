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


def save_syllabus(document: Document, outline: dict[str, Any]) -> Syllabus:
    """Replace any previous syllabus for this document.

    Regenerating is destructive by design: the chapters change, so the old topics'
    progress rows no longer point at anything a learner would recognise.
    """
    Syllabus.objects.filter(document=document).delete()

    syllabus = Syllabus.objects.create(
        document=document,
        title=outline["title"],
        subject=outline["subject"],
        description=outline["description"],
        language=outline["language"],
    )

    for chapter_data in outline["chapters"]:
        chapter = Chapter.objects.create(
            syllabus=syllabus,
            number=chapter_data["number"],
            title=chapter_data["title"],
            summary=chapter_data["summary"],
            page_start=chapter_data["page_start"],
            page_end=chapter_data["page_end"],
        )
        for position, topic_data in enumerate(chapter_data["topics"], start=1):
            Topic.objects.create(
                chapter=chapter,
                position=position,
                title=topic_data["title"],
                summary=topic_data["summary"],
                key_points=topic_data["key_points"],
                page_start=topic_data["page_start"],
                page_end=topic_data["page_end"],
            )

    return syllabus


def save_topic_content(topic: Topic, content: dict[str, Any]) -> None:
    """Replace this topic's content. Safe to call again after a failed attempt."""
    Lesson.objects.filter(topic=topic).delete()
    Quiz.objects.filter(topic=topic).delete()
    Exercise.objects.filter(topic=topic).delete()

    lesson = content["lesson"]
    Lesson.objects.create(
        topic=topic, title=lesson["title"], body_markdown=lesson["body_markdown"]
    )

    quiz = Quiz.objects.create(topic=topic)
    for position, question in enumerate(content["quiz"]["questions"], start=1):
        Question.objects.create(
            quiz=quiz,
            position=position,
            prompt=question["prompt"],
            choices=question["choices"],
            correct_index=question["correct_index"],
            explanation=question["explanation"],
        )

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
