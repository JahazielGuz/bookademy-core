"""The generation run: ordering, per-chapter completion, and the progress events."""

import pytest

from curriculum.models import Chapter, Syllabus, Topic
from documents.models import Document, GenerationEvent
from documents.tasks import process_document

OUTLINE = {
    "title": "Full Stack React",
    "subject": "React",
    "description": "Building apps with React.",
    "language": "javascript",
    "chapters": [
        {
            "number": 1,
            "title": "Getting started",
            "summary": "Setting up.",
            "page_start": 1,
            "page_end": 20,
            "topics": [
                {
                    "title": "Your first component",
                    "summary": "Components render markup.",
                    "key_points": ["Components are functions"],
                    "page_start": 2,
                    "page_end": 8,
                },
                {
                    "title": "Props",
                    "summary": "Passing data down.",
                    "key_points": ["Props are read-only"],
                    "page_start": 9,
                    "page_end": 20,
                },
            ],
        },
        {
            "number": 2,
            "title": "State",
            "summary": "State over time.",
            "page_start": 21,
            "page_end": 40,
            "topics": [
                {
                    "title": "useState",
                    "summary": "Local state.",
                    "key_points": ["State triggers a re-render"],
                    "page_start": 21,
                    "page_end": 40,
                }
            ],
        },
    ],
}

CONTENT = {
    "lesson": {"title": "A lesson", "body_markdown": "Body."},
    "quiz": {
        "questions": [
            {
                "prompt": "Why?",
                "choices": ["Because", "No"],
                "correct_index": 0,
                "explanation": "It is.",
            }
        ]
    },
    "exercises": [
        {
            "title": "Build it",
            "scenario_markdown": "A scenario.",
            "language": "javascript",
            "steps": [
                {
                    "number": 1,
                    "instruction_markdown": "Type this.",
                    "explanation_markdown": "It does a thing.",
                    "starter_code": "",
                    "expected_code": "const x = 1",
                    "hint": None,
                }
            ],
        }
    ],
}


@pytest.fixture
def stubbed_ai(monkeypatch):
    """Stand in for bookademy-ai, and record the order topics were asked for."""
    asked: list[str] = []

    monkeypatch.setattr(
        "documents.tasks.upload_document",
        lambda **kwargs: {"file_id": "file_stub", "page_count": 40},
    )
    monkeypatch.setattr(
        "documents.tasks.generate_syllabus", lambda **kwargs: OUTLINE
    )

    def topic_content(payload):
        asked.append(payload["topic_title"])
        return CONTENT

    monkeypatch.setattr("documents.tasks.request_topic_content", topic_content)
    return asked


@pytest.fixture
def uploaded(learner, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    return Document.objects.create(
        owner=learner, title="book", file="book.pdf", status=Document.Status.PENDING
    )


@pytest.mark.django_db(transaction=True)
def test_the_whole_run_completes(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.READY
    assert uploaded.page_count == 40
    assert Topic.objects.filter(status=Topic.Status.READY).count() == 3
    assert Syllabus.objects.get(document=uploaded).title == "Full Stack React"


@pytest.mark.django_db(transaction=True)
def test_chapters_are_written_in_order(uploaded, stubbed_ai):
    """Chapter 2's topics are not touched until chapter 1's are done, which is what
    makes "chapter 1 arrives first" true rather than a hope."""
    process_document.apply(args=[uploaded.id])

    assert stubbed_ai[:2] == ["Your first component", "Props"] or stubbed_ai[:2] == [
        "Props",
        "Your first component",
    ]
    # Whatever order the two topics inside chapter 1 ran in, chapter 2 came last.
    assert stubbed_ai[2] == "useState"


@pytest.mark.django_db(transaction=True)
def test_each_chapter_is_marked_ready_as_it_finishes(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    statuses = list(Chapter.objects.order_by("number").values_list("status", flat=True))
    assert statuses == [Chapter.Status.READY, Chapter.Status.READY]


@pytest.mark.django_db(transaction=True)
def test_the_event_log_tells_the_story_in_order(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    kinds = list(
        GenerationEvent.objects.filter(document=uploaded).values_list("kind", flat=True)
    )
    assert kinds[0] == GenerationEvent.Kind.STARTED
    assert kinds[1] == GenerationEvent.Kind.UPLOADED
    assert kinds[2] == GenerationEvent.Kind.SYLLABUS_READY
    assert kinds[-1] == GenerationEvent.Kind.DONE

    # Chapter 1 is announced and finished before chapter 2 is announced.
    chapter_events = [
        (event.kind, event.chapter_number)
        for event in GenerationEvent.objects.filter(
            document=uploaded,
            kind__in=[GenerationEvent.Kind.CHAPTER_STARTED, GenerationEvent.Kind.CHAPTER_READY],
        )
    ]
    assert chapter_events == [
        (GenerationEvent.Kind.CHAPTER_STARTED, 1),
        (GenerationEvent.Kind.CHAPTER_READY, 1),
        (GenerationEvent.Kind.CHAPTER_STARTED, 2),
        (GenerationEvent.Kind.CHAPTER_READY, 2),
    ]


@pytest.mark.django_db(transaction=True)
def test_a_failed_topic_leaves_its_chapter_incomplete_but_keeps_going(
    uploaded, stubbed_ai, monkeypatch
):
    """One bad topic must not cost the rest of the book."""
    from aiservice.client import AIServiceRefused

    def sometimes_refuses(payload):
        if payload["topic_title"] == "Props":
            raise AIServiceRefused("declined")
        return CONTENT

    monkeypatch.setattr("documents.tasks.request_topic_content", sometimes_refuses)

    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    # The run still finishes and chapter 2 is untouched by chapter 1's problem.
    assert uploaded.status == Document.Status.READY
    assert Chapter.objects.get(number=1).status == Chapter.Status.FAILED
    assert Chapter.objects.get(number=2).status == Chapter.Status.READY
    assert Topic.objects.get(title="Props").status == Topic.Status.FAILED
    assert Topic.objects.get(title="useState").status == Topic.Status.READY
