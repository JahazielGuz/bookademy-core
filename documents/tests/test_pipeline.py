"""The generation run: structure from the document, chapters in order, and the
page-slicing that makes a 600-page book affordable."""

import pytest

from curriculum.models import Chapter, Syllabus, Topic
from documents.models import Document, GenerationEvent
from documents.tasks import process_document

# Four pages, each identifiable so the slicing can be asserted.
PAGES = [
    "# Getting started\n```js\nconst a = 1\n```",
    "More of chapter one. UNIQUE_CH1_PAGE2",
    "# State\n```js\nconst [x, setX] = useState()\n```",
    "More of chapter two. UNIQUE_CH2_PAGE2",
]

DOCUMENT = {
    "page_count": 4,
    "has_outline": True,
    "pages": PAGES,
    "chapters": [
        {
            "number": 1,
            "title": "Getting started",
            "page_start": 1,
            "page_end": 2,
            "headings": [{"title": "Components", "page_start": 1, "page_end": 2}],
        },
        {
            "number": 2,
            "title": "State",
            "page_start": 3,
            "page_end": 4,
            "headings": [{"title": "useState", "page_start": 3, "page_end": 4}],
        },
    ],
}

TOPICS = {
    "topics": [
        {
            "title": "A topic",
            "summary": "It covers a thing.",
            "key_points": ["A point"],
            "page_start": 1,
            "page_end": 2,
        }
    ]
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
    """Stand in for bookademy-ai, recording what each call was sent."""
    sent: dict[str, list] = {"topics": [], "content": []}

    monkeypatch.setattr("documents.tasks.read_document", lambda **kwargs: DOCUMENT)

    def topics(payload):
        sent["topics"].append(payload)
        return TOPICS

    def content(payload):
        sent["content"].append(payload)
        return CONTENT

    monkeypatch.setattr("documents.tasks.chapter_topics", topics)
    monkeypatch.setattr("documents.tasks.request_topic_content", content)
    return sent


@pytest.fixture
def uploaded(learner, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "book.pdf").write_bytes(b"%PDF-1.4 stub")
    return Document.objects.create(
        owner=learner, title="book", file="book.pdf", status=Document.Status.PENDING
    )


@pytest.mark.django_db(transaction=True)
def test_the_whole_run_completes(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.READY
    assert uploaded.page_count == 4
    assert Chapter.objects.count() == 2
    assert Topic.objects.filter(status=Topic.Status.READY).count() == 2


@pytest.mark.django_db(transaction=True)
def test_chapters_and_page_ranges_come_from_the_document(uploaded, stubbed_ai):
    """Not from a model: the titles and ranges must be the book's own."""
    process_document.apply(args=[uploaded.id])

    chapters = list(Chapter.objects.order_by("number"))
    assert [c.title for c in chapters] == ["Getting started", "State"]
    assert (chapters[0].page_start, chapters[0].page_end) == (1, 2)
    assert (chapters[1].page_start, chapters[1].page_end) == (3, 4)


@pytest.mark.django_db(transaction=True)
def test_each_chapter_is_sent_only_its_own_pages(uploaded, stubbed_ai):
    """The cost of the whole system rests on this. A topic in chapter 2 must never be
    sent chapter 1's text."""
    process_document.apply(args=[uploaded.id])

    first, second = stubbed_ai["topics"]
    assert "UNIQUE_CH1_PAGE2" in first["text"]
    assert "UNIQUE_CH2_PAGE2" not in first["text"]
    assert "UNIQUE_CH2_PAGE2" in second["text"]
    assert "UNIQUE_CH1_PAGE2" not in second["text"]


@pytest.mark.django_db(transaction=True)
def test_no_pdf_is_ever_sent_to_a_model(uploaded, stubbed_ai):
    """Every generation call carries extracted text and nothing else."""
    process_document.apply(args=[uploaded.id])

    for payload in stubbed_ai["topics"] + stubbed_ai["content"]:
        assert "file_id" not in payload
        assert isinstance(payload["text"], str)


@pytest.mark.django_db(transaction=True)
def test_chapters_are_written_in_order(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    assert [p["chapter_number"] for p in stubbed_ai["topics"]] == [1, 2]
    assert [p["chapter_number"] for p in stubbed_ai["content"]] == [1, 2]


@pytest.mark.django_db(transaction=True)
def test_the_language_is_detected_from_the_book(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    assert Syllabus.objects.get().language == "javascript"


@pytest.mark.django_db(transaction=True)
def test_a_pdf_without_bookmarks_fails_with_a_readable_reason(uploaded, monkeypatch):
    monkeypatch.setattr(
        "documents.tasks.read_document",
        lambda **kwargs: {**DOCUMENT, "has_outline": False, "chapters": []},
    )

    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.FAILED
    assert "table of contents" in uploaded.error


@pytest.mark.django_db(transaction=True)
def test_a_failed_topic_does_not_cost_the_rest_of_the_book(uploaded, stubbed_ai, monkeypatch):
    from aiservice.client import AIServiceRefused

    def sometimes_refuses(payload):
        if payload["chapter_number"] == 1:
            raise AIServiceRefused("declined")
        return CONTENT

    monkeypatch.setattr("documents.tasks.request_topic_content", sometimes_refuses)

    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.READY
    assert Chapter.objects.get(number=1).status == Chapter.Status.FAILED
    assert Chapter.objects.get(number=2).status == Chapter.Status.READY


@pytest.mark.django_db(transaction=True)
def test_the_event_log_tells_the_story_in_order(uploaded, stubbed_ai):
    process_document.apply(args=[uploaded.id])

    pairs = [
        (e.kind, e.chapter_number)
        for e in GenerationEvent.objects.filter(
            document=uploaded,
            kind__in=[GenerationEvent.Kind.CHAPTER_STARTED, GenerationEvent.Kind.CHAPTER_READY],
        )
    ]
    assert pairs == [
        (GenerationEvent.Kind.CHAPTER_STARTED, 1),
        (GenerationEvent.Kind.CHAPTER_READY, 1),
        (GenerationEvent.Kind.CHAPTER_STARTED, 2),
        (GenerationEvent.Kind.CHAPTER_READY, 2),
    ]


@pytest.mark.django_db(transaction=True)
def test_a_redelivered_run_spends_nothing(uploaded, stubbed_ai):
    """The expensive bug, pinned.

    Celery redelivers a task it believes was lost, and a run longer than the broker's
    visibility timeout looks exactly like one. Without the lock the redelivered copy
    restarts from chapter one alongside the original. This asserts the second copy
    makes no model calls at all.
    """
    from documents.locks import document_run

    with document_run(uploaded.id) as held:
        assert held is not None
        process_document.apply(args=[uploaded.id])

    assert stubbed_ai["topics"] == []
    assert stubbed_ai["content"] == []
    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_the_run_takes_and_frees_its_own_lock(uploaded, stubbed_ai):
    """And having stood down once, a later run still works."""
    process_document.apply(args=[uploaded.id])
    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.READY

    from documents.locks import document_run

    with document_run(uploaded.id) as token:
        assert token is not None, "the finished run did not release its lock"


@pytest.mark.django_db(transaction=True)
def test_only_one_chapter_is_in_flight_at_a_time(uploaded, stubbed_ai):
    """Topics parallelise inside a chapter; chapters never overlap, or the syllabus
    stops filling in from the top."""
    seen: list[int] = []

    original = stubbed_ai
    import documents.tasks as tasks

    real = tasks.request_topic_content

    def recording(payload):
        seen.append(payload["chapter_number"])
        return real(payload)

    tasks.request_topic_content = recording
    try:
        process_document.apply(args=[uploaded.id])
    finally:
        tasks.request_topic_content = real

    # Every call for chapter 1 precedes every call for chapter 2.
    assert seen == sorted(seen), f"chapters interleaved: {seen}"
    del original


@pytest.mark.django_db(transaction=True)
def test_a_topic_is_sent_its_own_pages_not_its_chapter(uploaded, monkeypatch):
    """The seven-and-a-half-fold saving, pinned.

    A topic covers a handful of pages. Sending the whole chapter with it, once per
    topic, is what turned a few dollars into twenty.
    """
    wide_pages = [f"PAGE_{n}_CONTENT" for n in range(1, 21)]
    wide = {
        "page_count": 20,
        "has_outline": True,
        "pages": wide_pages,
        "chapters": [
            {
                "number": 1,
                "title": "A long chapter",
                "page_start": 1,
                "page_end": 20,
                "headings": [{"title": "A heading", "page_start": 1, "page_end": 20}],
            }
        ],
    }
    narrow_topic = {
        "topics": [
            {
                "title": "A narrow topic",
                "summary": "Covers a few pages.",
                "key_points": ["A point"],
                "page_start": 10,
                "page_end": 12,
            }
        ]
    }

    sent = {}
    monkeypatch.setattr("documents.tasks.read_document", lambda **kwargs: wide)
    monkeypatch.setattr("documents.tasks.chapter_topics", lambda p: (sent.update(chapter=p), narrow_topic)[1])
    monkeypatch.setattr("documents.tasks.request_topic_content", lambda p: (sent.update(topic=p), CONTENT)[1])

    process_document.apply(args=[uploaded.id])

    topic_text = sent["topic"]["text"]
    # Its own pages, plus one of margin either side so a listing is not cut in half.
    assert "PAGE_10_CONTENT" in topic_text
    assert "PAGE_12_CONTENT" in topic_text
    assert "PAGE_9_CONTENT" in topic_text
    assert "PAGE_13_CONTENT" in topic_text
    # ...and nothing like the whole chapter.
    assert "PAGE_1_CONTENT" not in topic_text
    assert "PAGE_20_CONTENT" not in topic_text

    # The chapter call still gets the whole chapter — it is choosing the topics.
    assert "PAGE_1_CONTENT" in sent["chapter"]["text"]
    assert "PAGE_20_CONTENT" in sent["chapter"]["text"]

    assert len(topic_text) < len(sent["chapter"]["text"]) / 2


@pytest.mark.django_db(transaction=True)
def test_the_chapter_text_carries_real_page_numbers(uploaded, stubbed_ai):
    """Without them the model counts from one.

    A chapter starting on page 28 then produces topics claiming pages 1-3, and every
    one of those topics is later sent the book's front matter instead of its own
    content — silently, because the text that arrives is still perfectly readable.
    """
    process_document.apply(args=[uploaded.id])

    second = stubbed_ai["topics"][1]
    assert "<!-- page 3 -->" in second["text"]
    assert "<!-- page 4 -->" in second["text"]
    assert second["page_start"] == 3
    assert second["page_end"] == 4


@pytest.mark.django_db(transaction=True)
def test_a_topic_cannot_point_outside_its_chapter(uploaded, monkeypatch):
    """A backstop for a model that ignores the page markers: being imprecise inside
    the chapter is survivable, pointing at another part of the book is not."""
    out_of_range = {
        "topics": [
            {
                "title": "A topic with nonsense pages",
                "summary": "s",
                "key_points": ["k"],
                "page_start": 1,
                "page_end": 999,
            }
        ]
    }
    monkeypatch.setattr("documents.tasks.read_document", lambda **kwargs: DOCUMENT)
    monkeypatch.setattr("documents.tasks.chapter_topics", lambda p: out_of_range)
    monkeypatch.setattr("documents.tasks.request_topic_content", lambda p: CONTENT)

    process_document.apply(args=[uploaded.id])

    from curriculum.models import Topic

    topic = Topic.objects.filter(chapter__number=2).first()
    assert topic.page_start >= 3
    assert topic.page_end <= 4
