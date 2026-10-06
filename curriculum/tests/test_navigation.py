import pytest

from curriculum.models import Topic
from progress.models import QuizAttempt, StepCompletion


def _topic(chapter, position, title, status=Topic.Status.READY):
    return Topic.objects.create(
        chapter=chapter,
        position=position,
        title=title,
        summary=f"About {title}.",
        key_points=[],
        page_start=20,
        page_end=24,
        status=status,
    )


@pytest.mark.django_db
def test_a_lesson_leads_to_its_own_quiz(api, course):
    response = api.get(f"/api/topics/{course['topic'].id}/")

    assert response.data["lesson_links"]["previous"] is None
    assert response.data["lesson_links"]["next"] == {
        "topic_id": course["topic"].id,
        "part": "quiz",
    }


@pytest.mark.django_db
def test_a_quiz_leads_to_the_next_topics_lesson(api, course):
    second = _topic(course["chapter"], 2, "Global scope")

    response = api.get(f"/api/topics/{course['topic'].id}/")

    assert response.data["quiz_links"]["previous"] == {
        "topic_id": course["topic"].id,
        "part": "lesson",
    }
    assert response.data["quiz_links"]["next"] == {"topic_id": second.id, "part": "lesson"}


@pytest.mark.django_db
def test_the_last_item_in_the_syllabus_leads_nowhere(api, course):
    response = api.get(f"/api/topics/{course['topic'].id}/")

    assert response.data["quiz_links"]["next"] is None


@pytest.mark.django_db
def test_a_topic_still_being_written_is_not_somewhere_next_can_send_you(api, course):
    _topic(course["chapter"], 2, "Global scope", status=Topic.Status.PENDING)

    response = api.get(f"/api/topics/{course['topic'].id}/")

    # Next would otherwise open a page with nothing on it.
    assert response.data["quiz_links"]["next"] is None


@pytest.mark.django_db
def test_a_lesson_counts_as_done_only_once_every_checkpoint_is(api, course, learner):
    steps = course["steps"]
    StepCompletion.objects.create(user=learner, step=steps[0], submitted_code="x = 1")

    response = api.get(f"/api/topics/{course['topic'].id}/")
    assert response.data["lesson_complete"] is False

    StepCompletion.objects.create(user=learner, step=steps[1], submitted_code="x = 2")

    response = api.get(f"/api/topics/{course['topic'].id}/")
    assert response.data["lesson_complete"] is True


@pytest.mark.django_db
def test_a_quiz_counts_as_done_only_on_a_full_score(api, course, learner):
    QuizAttempt.objects.create(user=learner, quiz=course["quiz"], answers={}, score=1, total=2)

    response = api.get(f"/api/topics/{course['topic'].id}/")
    assert response.data["quiz_passed"] is False

    QuizAttempt.objects.create(user=learner, quiz=course["quiz"], answers={}, score=2, total=2)

    response = api.get(f"/api/topics/{course['topic'].id}/")
    assert response.data["quiz_passed"] is True
