"""The progress stream."""

import json

import pytest
from rest_framework.test import APIClient

from documents.models import Document, GenerationEvent


def frames(response) -> list[dict]:
    """Pull the data payloads out of an SSE body, ignoring comments and heartbeats."""
    body = b"".join(response.streaming_content).decode()
    return [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def run(course):
    """A finished run with three events, so the stream drains and closes."""
    document = course["document"]
    for kind, message, chapter in [
        (GenerationEvent.Kind.STARTED, "Reading your PDF.", None),
        (GenerationEvent.Kind.CHAPTER_READY, "Chapter 1 is ready: Scope", 1),
        (GenerationEvent.Kind.DONE, "All 1 chapters are ready.", None),
    ]:
        GenerationEvent.objects.create(
            document=document, kind=kind, message=message, chapter_number=chapter
        )
    return document


@pytest.mark.django_db
def test_the_stream_is_an_event_stream(api, run):
    response = api.get(f"/api/documents/{run.id}/events/")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache"


@pytest.mark.django_db
def test_every_event_arrives_in_order(api, run):
    payloads = frames(api.get(f"/api/documents/{run.id}/events/"))

    assert [p["kind"] for p in payloads] == ["started", "chapter_ready", "done"]
    assert payloads[1]["chapter_number"] == 1
    assert payloads[1]["message"] == "Chapter 1 is ready: Scope"


@pytest.mark.django_db
def test_a_cursor_skips_what_was_already_seen(api, run):
    first = frames(api.get(f"/api/documents/{run.id}/events/"))[0]

    payloads = frames(api.get(f"/api/documents/{run.id}/events/?since={first['id']}"))

    assert [p["kind"] for p in payloads] == ["chapter_ready", "done"]


@pytest.mark.django_db
def test_a_reconnect_resumes_from_last_event_id(api, run):
    payloads = frames(api.get(f"/api/documents/{run.id}/events/"))
    second = payloads[1]["id"]

    resumed = frames(
        api.get(f"/api/documents/{run.id}/events/", headers={"Last-Event-ID": str(second)})
    )

    assert [p["kind"] for p in resumed] == ["done"]


@pytest.mark.django_db
def test_a_nonsense_cursor_does_not_break_the_stream(api, run):
    payloads = frames(api.get(f"/api/documents/{run.id}/events/?since=banana"))

    assert [p["kind"] for p in payloads] == ["started", "chapter_ready", "done"]


@pytest.mark.django_db
def test_another_learner_cannot_watch_your_run(run, stranger):
    client = APIClient()
    client.force_authenticate(user=stranger)

    assert client.get(f"/api/documents/{run.id}/events/").status_code == 404


@pytest.mark.django_db
def test_a_failed_run_still_closes_the_stream(api, course):
    document = course["document"]
    document.status = Document.Status.FAILED
    document.save(update_fields=["status"])
    GenerationEvent.objects.create(
        document=document, kind=GenerationEvent.Kind.FAILED, message="It went wrong."
    )

    payloads = frames(api.get(f"/api/documents/{document.id}/events/"))

    assert [p["kind"] for p in payloads] == ["failed"]
