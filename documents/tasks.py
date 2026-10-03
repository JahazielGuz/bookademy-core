"""The generation pipeline.

    upload the PDF  ->  write the syllabus  ->  chapter 1, then 2, then 3 ...

Chapters are written strictly in order so that chapter 1 becomes usable within a
minute or two and the syllabus fills in from the top. Within one chapter the topics
run concurrently, because each is an independent HTTP call that spends its life
waiting.

This is one long task rather than a fan-out. It keeps the ordering obvious, writes
progress events in the order they happen, and resumes cleanly: topics already marked
ready are skipped, so a retry picks up where it stopped.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from django.db import close_old_connections, transaction

from aiservice.client import AIServiceError, AIServiceRefused, generate_syllabus
from aiservice.client import generate_topic_content as request_topic_content
from aiservice.client import upload_document
from curriculum.builders import save_syllabus, save_topic_content
from curriculum.models import Chapter, Topic
from documents import events
from documents.models import Document

logger = logging.getLogger(__name__)

TOPIC_CONCURRENCY = 3


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_document(self, document_id: int) -> None:
    document = Document.objects.get(pk=document_id)

    try:
        syllabus = _prepare(document)
    except AIServiceRefused as exc:
        _fail(document, f"The model declined this document: {exc}")
        return
    except AIServiceError as exc:
        if self.request.retries >= self.max_retries:
            _fail(document, str(exc))
            return
        raise self.retry(exc=exc) from exc

    chapters = list(syllabus.chapters.all())
    for chapter in chapters:
        _write_chapter(document, chapter)

    _settle(document, len(chapters))


def _prepare(document: Document):
    """Upload the PDF and turn it into a syllabus. Skipped on a resume."""
    if hasattr(document, "syllabus"):
        return document.syllabus

    document.status = Document.Status.UPLOADING
    document.save(update_fields=["status", "updated_at"])
    events.started(document)

    with document.file.open("rb") as handle:
        uploaded = upload_document(
            filename=document.file.name.rsplit("/", 1)[-1], content=handle.read()
        )

    document.ai_file_id = uploaded["file_id"]
    document.page_count = uploaded["page_count"]
    document.status = Document.Status.OUTLINING
    document.save(update_fields=["ai_file_id", "page_count", "status", "updated_at"])
    events.uploaded(document, uploaded["page_count"])

    outline = generate_syllabus(file_id=document.ai_file_id)

    with transaction.atomic():
        syllabus = save_syllabus(document, outline)
        document.title = syllabus.title
        document.status = Document.Status.GENERATING
        document.save(update_fields=["title", "status", "updated_at"])

    topics = Topic.objects.filter(chapter__syllabus=syllabus).count()
    events.syllabus_ready(document, syllabus.chapters.count(), topics)
    return syllabus


def _write_chapter(document: Document, chapter: Chapter) -> None:
    """Write every topic in one chapter, then mark the chapter ready.

    The chapter only reaches `ready` when all of its topics did, so a chapter that
    appears in the syllabus is a chapter a learner can actually work through.
    """
    pending = [t for t in chapter.topics.all() if t.status != Topic.Status.READY]
    if not pending:
        _mark_chapter(document, chapter)
        return

    chapter.status = Chapter.Status.GENERATING
    chapter.save(update_fields=["status"])
    events.chapter_started(document, chapter.number, chapter.title, len(pending))

    total = chapter.topics.count()
    with ThreadPoolExecutor(max_workers=TOPIC_CONCURRENCY) as pool:
        results = list(pool.map(_write_topic, pending))

    for topic, ok in zip(pending, results):
        if ok:
            done = chapter.topics.filter(status=Topic.Status.READY).count()
            events.topic_ready(document, chapter.number, topic.title, done, total)
        else:
            events.failed(
                document,
                f"Could not write “{topic.title}”. Moving on.",
                chapter_number=chapter.number,
            )

    _mark_chapter(document, chapter)


def _write_topic(topic: Topic) -> bool:
    """One topic, in its own thread. Returns whether it succeeded.

    Each thread gets its own database connection, so it must hand it back rather
    than leave it open for the life of the task.
    """
    close_old_connections()
    try:
        document = topic.chapter.syllabus.document
        topic.status = Topic.Status.GENERATING
        topic.save(update_fields=["status"])

        content = request_topic_content(
            {
                "file_id": document.ai_file_id,
                "language": topic.chapter.syllabus.language,
                "chapter_number": topic.chapter.number,
                "chapter_title": topic.chapter.title,
                "topic_title": topic.title,
                "topic_summary": topic.summary,
                "key_points": topic.key_points,
                "page_start": topic.page_start,
                "page_end": topic.page_end,
            }
        )

        with transaction.atomic():
            save_topic_content(topic, content)
            topic.status = Topic.Status.READY
            topic.error = ""
            topic.save(update_fields=["status", "error"])
        return True

    except (AIServiceError, AIServiceRefused) as exc:
        logger.warning("topic %s failed: %s", topic.pk, exc)
        topic.status = Topic.Status.FAILED
        topic.error = str(exc)
        topic.save(update_fields=["status", "error"])
        return False
    finally:
        close_old_connections()


def _mark_chapter(document: Document, chapter: Chapter) -> None:
    ready = chapter.topics.filter(status=Topic.Status.READY).count()
    total = chapter.topics.count()

    chapter.status = Chapter.Status.READY if ready == total else Chapter.Status.FAILED
    chapter.save(update_fields=["status"])

    if chapter.status == Chapter.Status.READY:
        events.chapter_ready(document, chapter.number, chapter.title)
    else:
        events.failed(
            document,
            f"Chapter {chapter.number} is incomplete — {ready} of {total} topics written.",
            chapter_number=chapter.number,
        )


def _settle(document: Document, chapters: int) -> None:
    any_ready = Topic.objects.filter(
        chapter__syllabus__document=document, status=Topic.Status.READY
    ).exists()

    if any_ready:
        document.status = Document.Status.READY
        document.error = ""
        document.save(update_fields=["status", "error", "updated_at"])
        events.done(document, chapters)
    else:
        _fail(document, "Every topic failed to generate.")


def _fail(document: Document, message: str) -> None:
    logger.error("document %s failed: %s", document.pk, message)
    document.status = Document.Status.FAILED
    document.error = message
    document.save(update_fields=["status", "error", "updated_at"])
    events.failed(document, message)
