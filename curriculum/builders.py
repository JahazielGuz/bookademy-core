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


def save_structure(document: Document, data: dict[str, Any], language: str) -> Syllabus:
    """Create the syllabus and its chapters from the document's own structure.

    No model produced any of this: the chapters, their titles and their page ranges
    come from the PDF's bookmarks. Topics are not created here — each chapter's are
    worked out when that chapter is reached.
    """
    Syllabus.objects.filter(document=document).delete()

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


def save_topics(chapter: Chapter, topics: list[dict[str, Any]]) -> list[Topic]:
    """Replace this chapter's topics. Safe to call again after a failed attempt."""
    Topic.objects.filter(chapter=chapter).delete()

    return [
        Topic.objects.create(
            chapter=chapter,
            position=position,
            title=topic["title"],
            summary=topic["summary"],
            key_points=topic["key_points"],
            page_start=topic["page_start"],
            page_end=topic["page_end"],
        )
        for position, topic in enumerate(topics, start=1)
    ]


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
