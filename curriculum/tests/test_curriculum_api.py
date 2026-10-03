import pytest

from progress.models import QuizAttempt
from progress.models import StepCompletion


@pytest.mark.django_db
def test_syllabus_lists_chapters_and_topics(api, course):
    document = course["document"]
    response = api.get(f"/api/documents/{document.id}/syllabus/")

    assert response.status_code == 200
    assert response.data["title"] == "Learning Python"
    assert len(response.data["chapters"]) == 1

    topic = response.data["chapters"][0]["topics"][0]
    assert topic["steps_total"] == 2
    assert topic["steps_completed"] == 0
    assert topic["quiz_passed"] is False
    assert topic["complete"] is False


@pytest.mark.django_db
def test_a_topic_is_only_complete_with_every_step_and_the_quiz(api, course, learner):
    document, topic, quiz = course["document"], course["topic"], course["quiz"]

    for step in course["steps"]:
        StepCompletion.objects.create(user=learner, step=step, submitted_code=step.expected_code)

    response = api.get(f"/api/documents/{document.id}/syllabus/")
    row = response.data["chapters"][0]["topics"][0]
    assert row["steps_completed"] == 2
    # Every step passed but the quiz has not been: not complete yet.
    assert row["complete"] is False

    QuizAttempt.objects.create(user=learner, quiz=quiz, answers={}, score=2, total=2)

    response = api.get(f"/api/documents/{document.id}/syllabus/")
    row = response.data["chapters"][0]["topics"][0]
    assert row["quiz_passed"] is True
    assert row["complete"] is True
    del topic


@pytest.mark.django_db
def test_a_failed_quiz_attempt_does_not_count_as_passed(api, course, learner):
    QuizAttempt.objects.create(user=learner, quiz=course["quiz"], answers={}, score=1, total=2)

    response = api.get(f"/api/documents/{course['document'].id}/syllabus/")

    assert response.data["chapters"][0]["topics"][0]["quiz_passed"] is False


@pytest.mark.django_db
def test_topic_detail_carries_the_ghost_text_target(api, course):
    response = api.get(f"/api/topics/{course['topic'].id}/")

    assert response.status_code == 200
    step = response.data["exercises"][0]["steps"][0]
    # The editor renders the grey text from this, so it has to be present.
    assert step["expected_code"].startswith("def favorite_color():")
    assert step["unlocked"] is True
    assert step["completed"] is False
    # The second step is closed until the first is passed.
    assert response.data["exercises"][0]["steps"][1]["unlocked"] is False


@pytest.mark.django_db
def test_topic_detail_withholds_the_quiz_answers(api, course):
    response = api.get(f"/api/topics/{course['topic'].id}/")

    question = response.data["quiz"]["questions"][0]
    assert "correct_index" not in question
    assert "explanation" not in question
    assert question["choices"] == ["Local scope", "Global scope"]


@pytest.mark.django_db
def test_another_learner_cannot_read_the_syllabus(course, stranger):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=stranger)

    assert client.get(f"/api/documents/{course['document'].id}/syllabus/").status_code == 404
    assert client.get(f"/api/topics/{course['topic'].id}/").status_code == 404
