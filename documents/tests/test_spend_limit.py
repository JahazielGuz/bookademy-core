"""The brake.

Every other guard here reduces cost or reports it. This is the only one that stops
it, which is what was missing when a run projected at $5 cost $20.
"""

import pytest

from curriculum.models import Chapter, Topic
from documents.models import Document, GenerationEvent, UsageRecord
from documents.spend import SpendLimitReached, check_budget, spent_on
from documents.tasks import process_document
from documents.tests.test_pipeline import CONTENT, DOCUMENT, TOPICS  # noqa: F401


@pytest.fixture
def uploaded(learner, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "book.pdf").write_bytes(b"%PDF-1.4 stub")
    return Document.objects.create(
        owner=learner, title="book", file="book.pdf", status=Document.Status.PENDING
    )


def bill(document, dollars: float):
    """Record usage costing roughly `dollars` on gpt-5-mini output at $2.00/M."""
    UsageRecord.objects.create(
        document=document,
        kind=UsageRecord.Kind.CONTENT,
        model="gpt-5-mini",
        input_tokens=0,
        output_tokens=int(dollars / 2.00 * 1_000_000),
    )


@pytest.mark.django_db
def test_spend_is_summed_from_recorded_usage(uploaded):
    bill(uploaded, 0.75)
    bill(uploaded, 0.25)

    assert spent_on(uploaded) == pytest.approx(1.0)


@pytest.mark.django_db
def test_under_the_limit_passes(uploaded, settings):
    settings.DOCUMENT_SPEND_LIMIT_USD = 2.00
    bill(uploaded, 1.99)

    check_budget(uploaded)  # must not raise


@pytest.mark.django_db
def test_at_the_limit_stops(uploaded, settings):
    settings.DOCUMENT_SPEND_LIMIT_USD = 2.00
    bill(uploaded, 2.00)

    with pytest.raises(SpendLimitReached):
        check_budget(uploaded)


@pytest.mark.django_db
def test_a_zero_limit_means_no_ceiling(uploaded, settings):
    settings.DOCUMENT_SPEND_LIMIT_USD = 0
    bill(uploaded, 500.00)

    check_budget(uploaded)  # must not raise


@pytest.mark.django_db
def test_the_message_says_what_was_spent_and_what_to_change(uploaded, settings):
    settings.DOCUMENT_SPEND_LIMIT_USD = 2.00
    bill(uploaded, 2.50)

    with pytest.raises(SpendLimitReached) as raised:
        check_budget(uploaded)

    message = str(raised.value)
    assert "$2.00" in message
    assert "$2.50" in message
    assert "DOCUMENT_SPEND_LIMIT_USD" in message
    assert "kept" in message


@pytest.mark.django_db(transaction=True)
def test_a_run_stops_at_the_ceiling_and_keeps_what_it_made(uploaded, settings, monkeypatch):
    """The point of the whole thing: stop, keep what was paid for, say why."""
    settings.DOCUMENT_SPEND_LIMIT_USD = 2.00

    calls = {"content": 0}

    def expensive_content(payload):
        calls["content"] += 1
        # One topic costs $2.50, so the ceiling is already passed when the next is
        # checked. The budget is checked before a call, never after, so the overshoot
        # is bounded by the single call in flight.
        return {
            **CONTENT,
            "usage": {
                "model": "gpt-5-mini",
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 1_250_000,
            },
        }

    monkeypatch.setattr("documents.tasks.read_document", lambda **kwargs: DOCUMENT)
    monkeypatch.setattr("documents.tasks.chapter_topics", lambda p: TOPICS)
    monkeypatch.setattr("documents.tasks.request_topic_content", expensive_content)

    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.FAILED
    assert "limit" in uploaded.error

    # It stopped after the first topic rather than working through the book.
    assert calls["content"] == 1

    # And what was generated before the ceiling is still there and usable.
    assert Topic.objects.filter(status=Topic.Status.READY).count() >= 1

    assert GenerationEvent.objects.filter(
        document=uploaded, kind=GenerationEvent.Kind.FAILED
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_a_cheap_run_is_not_stopped(uploaded, settings, monkeypatch):
    settings.DOCUMENT_SPEND_LIMIT_USD = 2.00

    cheap = {
        "model": "gpt-5-mini",
        "input_tokens": 100,
        "cached_input_tokens": 0,
        "output_tokens": 100,
    }
    monkeypatch.setattr("documents.tasks.read_document", lambda **kwargs: DOCUMENT)
    monkeypatch.setattr("documents.tasks.chapter_topics", lambda p: {**TOPICS, "usage": cheap})
    monkeypatch.setattr(
        "documents.tasks.request_topic_content", lambda p: {**CONTENT, "usage": cheap}
    )

    process_document.apply(args=[uploaded.id])

    uploaded.refresh_from_db()
    assert uploaded.status == Document.Status.READY
    assert Chapter.objects.filter(status=Chapter.Status.READY).count() == 2
