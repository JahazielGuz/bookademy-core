"""Server-sent events for a generation run.

The browser opens one of these per course page and receives each progress event as
it is written. The row id is the SSE event id, so when the connection drops the
browser's automatic reconnect carries `Last-Event-ID` and resumes from there rather
than replaying the run.

The generator polls the event table rather than subscribing to a message bus: the
events it is waiting for are produced at the pace of model calls — tens of seconds
apart — so a one-second read loop is imperceptible, and it keeps the event log the
single source of truth instead of adding a second one.

The cost of a real stream is a held thread and database connection per open page.
The stream therefore closes itself after MAX_LIFETIME, and lets the browser's own
reconnect start a fresh one.
"""

import json
import time
from collections.abc import Iterator

from django.db import close_old_connections

from documents.models import Document, GenerationEvent

POLL_SECONDS = 1.0
MAX_LIFETIME_SECONDS = 600
HEARTBEAT_SECONDS = 15

TERMINAL = {Document.Status.READY, Document.Status.FAILED}


def frame(event: GenerationEvent) -> str:
    payload = {
        "id": event.id,
        "kind": event.kind,
        "message": event.message,
        "chapter_number": event.chapter_number,
    }
    return f"id: {event.id}\ndata: {json.dumps(payload)}\n\n"


def stream(document_id: int, since: int) -> Iterator[str]:
    last = since
    started = time.monotonic()
    last_beat = started

    while time.monotonic() - started < MAX_LIFETIME_SECONDS:
        close_old_connections()

        new = list(
            GenerationEvent.objects.filter(document_id=document_id, id__gt=last).order_by("id")
        )
        for event in new:
            yield frame(event)
            last = event.id

        status = (
            Document.objects.filter(pk=document_id).values_list("status", flat=True).first()
        )
        # Stop only once the run is over *and* this pass drained nothing, so the
        # final events are never cut off by the status flipping mid-write.
        if status in TERMINAL and not new:
            yield ": complete\n\n"
            return

        now = time.monotonic()
        if now - last_beat >= HEARTBEAT_SECONDS:
            # Keeps proxies from closing an idle connection during a long model call.
            yield ": keep-alive\n\n"
            last_beat = now

        time.sleep(POLL_SECONDS)
