"""Shared fixtures. A whole course tree, because almost every endpoint needs one."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

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

User = get_user_model()


@pytest.fixture
def learner(db):
    return User.objects.create_user(email="learner@example.com", password="correct-horse-99")


@pytest.fixture
def stranger(db):
    return User.objects.create_user(email="stranger@example.com", password="correct-horse-99")


@pytest.fixture
def api(learner):
    client = APIClient()
    client.force_authenticate(user=learner)
    return client


@pytest.fixture
def course(learner):
    """One document, one chapter, one ready topic with a lesson, a 2-question quiz
    and a 2-step exercise."""
    document = Document.objects.create(
        owner=learner,
        title="Learning Python",
        file="documents/learning-python.pdf",
        page_count=120,
        ai_file_id="file_test",
        status=Document.Status.READY,
    )
    syllabus = Syllabus.objects.create(
        document=document,
        title="Learning Python",
        subject="Python programming",
        description="A course from the book.",
        language="python",
    )
    chapter = Chapter.objects.create(
        syllabus=syllabus,
        number=1,
        title="Scope",
        summary="Where names live.",
        page_start=10,
        page_end=30,
    )
    topic = Topic.objects.create(
        chapter=chapter,
        position=1,
        title="Local scope",
        summary="Names created in a function are local to it.",
        key_points=["A function body is its own namespace"],
        page_start=12,
        page_end=18,
        status=Topic.Status.READY,
    )
    Lesson.objects.create(topic=topic, title="Local scope", body_markdown="Names are local.")

    quiz = Quiz.objects.create(topic=topic)
    Question.objects.create(
        quiz=quiz,
        position=1,
        prompt="Where does `color` live?",
        choices=["Local scope", "Global scope"],
        correct_index=0,
        explanation="It is assigned inside the function.",
    )
    Question.objects.create(
        quiz=quiz,
        position=2,
        prompt="What does printing it outside raise?",
        choices=["NameError", "TypeError"],
        correct_index=0,
        explanation="The name does not exist out there.",
    )

    exercise = Exercise.objects.create(
        topic=topic,
        position=1,
        title="Print a colour",
        scenario_markdown="A paint shop app.",
        language="python",
    )
    first = ExerciseStep.objects.create(
        exercise=exercise,
        number=1,
        instruction_markdown="Define `favorite_color`.",
        explanation_markdown="A function groups the work.",
        starter_code="",
        expected_code="def favorite_color():\n    color = 'Red'",
    )
    second = ExerciseStep.objects.create(
        exercise=exercise,
        number=2,
        instruction_markdown="Print the colour inside the function.",
        explanation_markdown="Printing inside keeps it in local scope.",
        starter_code="def favorite_color():\n    color = 'Red'",
        expected_code="def favorite_color():\n    color = 'Red'\n    print(color)",
    )

    return {
        "document": document,
        "syllabus": syllabus,
        "chapter": chapter,
        "topic": topic,
        "quiz": quiz,
        "exercise": exercise,
        "steps": [first, second],
    }
