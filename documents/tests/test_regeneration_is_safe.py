"""Re-running generation must never destroy what a run already paid for.

The builders delete before they write, and three guards in the task keep them from
reaching anything finished. Those guards exist for resumability rather than for
safety, which means a refactor could remove them without anyone noticing. These
tests make the protection the point rather than a side effect.
"""

import pytest

from curriculum.models import Chapter, Exercise, ExerciseStep, Lesson, Question, Topic
from documents.models import Document
from documents.tasks import process_document
from documents.tests.test_pipeline import CONTENT, DOCUMENT, TOPICS  # noqa: F401


@pytest.fixture
def uploaded(learner, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "book.pdf").write_bytes(b"%PDF-1.4 stub")
    return Document.objects.create(
        owner=learner, title="book", file="book.pdf", status=Document.Status.PENDING
    )


@pytest.fixture
def generated(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])
    uploaded.refresh_from_db()
    return uploaded


@pytest.fixture
def stubbed_ai(monkeypatch):
    sent = {"topics": [], "content": []}
    monkeypatch.setattr("documents.tasks.read_document", lambda **kwargs: DOCUMENT)
    monkeypatch.setattr(
        "documents.tasks.chapter_topics", lambda p: (sent["topics"].append(p), TOPICS)[1]
    )
    monkeypatch.setattr(
        "documents.tasks.request_topic_content", lambda p: (sent["content"].append(p), CONTENT)[1]
    )
    return sent


def census():
    return {
        "chapters": Chapter.objects.count(),
        "topics": Topic.objects.count(),
        "lessons": Lesson.objects.count(),
        "questions": Question.objects.count(),
        "exercises": Exercise.objects.count(),
        "checkpoints": ExerciseStep.objects.count(),
    }


@pytest.mark.django_db(transaction=True)
def test_re_running_destroys_nothing(generated, stubbed_ai):
    before = census()
    assert before["checkpoints"] > 0

    process_document.apply(args=[generated.id])

    assert census() == before


@pytest.mark.django_db(transaction=True)
def test_re_running_spends_nothing(generated, stubbed_ai):
    """Nothing to redo means nothing to pay for."""
    stubbed_ai["topics"].clear()
    stubbed_ai["content"].clear()

    process_document.apply(args=[generated.id])

    assert stubbed_ai["topics"] == []
    assert stubbed_ai["content"] == []


@pytest.mark.django_db(transaction=True)
def test_the_identical_checkpoints_survive(generated, stubbed_ai):
    """Not just the same count — the same rows, with the same ids and code."""
    before = {
        (s.id, s.expected_code) for s in ExerciseStep.objects.all()
    }

    process_document.apply(args=[generated.id])

    assert {(s.id, s.expected_code) for s in ExerciseStep.objects.all()} == before


@pytest.mark.django_db(transaction=True)
def test_a_gap_is_filled_without_touching_the_rest(generated, stubbed_ai):
    """Resuming is still possible: an unfinished topic is completed, and everything
    already written is left exactly as it was."""
    gap = Topic.objects.filter(status=Topic.Status.READY).last()
    survivors = {(s.id, s.expected_code) for s in ExerciseStep.objects.exclude(exercise__topic=gap)}

    gap.status = Topic.Status.PENDING
    gap.save(update_fields=["status"])

    process_document.apply(args=[generated.id])

    gap.refresh_from_db()
    assert gap.status == Topic.Status.READY
    assert {
        (s.id, s.expected_code) for s in ExerciseStep.objects.exclude(exercise__topic=gap)
    } == survivors


@pytest.mark.django_db(transaction=True)
def test_the_builders_refuse_to_overwrite_a_syllabus(generated):
    """The guard that makes the protection enforced rather than incidental."""
    from curriculum.builders import WouldDestroyContent, save_structure

    with pytest.raises(WouldDestroyContent) as raised:
        save_structure(generated, DOCUMENT, "javascript")

    assert "replace=True" in str(raised.value)


@pytest.mark.django_db(transaction=True)
def test_the_builders_refuse_to_overwrite_a_chapters_topics(generated):
    from curriculum.builders import WouldDestroyContent, save_topics

    chapter = Chapter.objects.first()

    with pytest.raises(WouldDestroyContent):
        save_topics(chapter, TOPICS["topics"])


@pytest.mark.django_db(transaction=True)
def test_the_builders_refuse_to_overwrite_a_finished_topic(generated):
    from curriculum.builders import WouldDestroyContent, save_topic_content

    topic = Topic.objects.filter(status=Topic.Status.READY).first()

    with pytest.raises(WouldDestroyContent):
        save_topic_content(topic, CONTENT)


@pytest.mark.django_db(transaction=True)
def test_explicit_replacement_is_still_possible(generated):
    """Refusing by default is the point; refusing always would make a genuine
    regeneration impossible."""
    from curriculum.builders import save_structure

    save_structure(generated, DOCUMENT, "javascript", replace=True)

    assert Chapter.objects.count() == len(DOCUMENT["chapters"])
