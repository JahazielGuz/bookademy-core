"""The generation pipeline.

    read the PDF  ->  chapter 1, then chapter 2, then chapter 3 ...

There is no whole-book model call. The chapters, their titles and their page ranges
are read from the document's own bookmarks, which is exact, free, and incapable of
inventing a chapter the book does not have. A model is only asked the things the
document cannot answer: which of a chapter's headings are really one topic, and what
the lesson for each should say.

Chapters are written strictly in order so chapter one becomes usable within a minute
or two and the syllabus fills in from the top. Within one chapter the topics run
concurrently, because each is an independent HTTP call that spends its life waiting.

This is one long task rather than a fan-out. It keeps the ordering obvious, writes
progress events in the order they happen, and resumes cleanly: topics already marked
ready are skipped, so a retry picks up where it stopped.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from django.db import close_old_connections, transaction

from aiservice.client import AIServiceError, AIServiceRefused, chapter_topics, read_document
from aiservice.client import topic_content as request_topic_content
from curriculum.builders import save_structure, save_topic_content, save_topics
from curriculum.models import Chapter, Topic
from documents import events
from documents.language import detect_language
from documents.models import Document

logger = logging.getLogger(__name__)

TOPIC_CONCURRENCY = 3


class NoOutline(Exception):
    """The PDF carries no usable bookmarks, so its structure cannot be read."""


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_document(self, document_id: int) -> None:
    document = Document.objects.get(pk=document_id)

    try:
        syllabus = _prepare(document)
    except AIServiceRefused as exc:
        _fail(document, f"The model declined this document: {exc}")
        return
    except NoOutline as exc:
        _fail(document, str(exc))
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
    """Read the PDF and lay out the syllabus. Skipped on a resume."""
    if hasattr(document, "syllabus"):
        return document.syllabus

    document.status = Document.Status.UPLOADING
    document.save(update_fields=["status", "updated_at"])
    events.started(document)

    with document.file.open("rb") as handle:
        data = read_document(
            filename=document.file.name.rsplit("/", 1)[-1], content=handle.read()
        )

    if not data["has_outline"]:
        raise NoOutline(
            "This PDF has no table of contents to read its chapters from. "
            "Books exported without bookmarks are not supported yet."
        )

    document.pages = data["pages"]
    document.page_count = data["page_count"]
    document.status = Document.Status.OUTLINING
    document.save(update_fields=["pages", "page_count", "status", "updated_at"])
    events.uploaded(document, data["page_count"])

    language = detect_language(data["pages"])

    with transaction.atomic():
        syllabus = save_structure(document, data, language)
        document.status = Document.Status.GENERATING
        document.save(update_fields=["status", "updated_at"])

    events.syllabus_ready(document, len(data["chapters"]), 0)
    return syllabus


def chapter_text(document: Document, chapter: Chapter) -> str:
    """The chapter's own pages, sliced from the text extracted once up front.

    This is what makes a 600-page book affordable: a topic is sent its chapter, not
    the book.
    """
    pages = document.pages or []
    start = max(0, chapter.page_start - 1)
    end = min(len(pages), chapter.page_end)
    return "\n\n".join(pages[start:end])


def _write_chapter(document: Document, chapter: Chapter) -> None:
    """Work out the chapter's topics, write them all, then mark it ready."""
    chapter.status = Chapter.Status.GENERATING
    chapter.save(update_fields=["status"])

    text = chapter_text(document, chapter)
    language = chapter.syllabus.language

    existing = list(chapter.topics.all())
    if not existing:
        try:
            response = chapter_topics(
                {
                    "language": language,
                    "chapter_number": chapter.number,
                    "chapter_title": chapter.title,
                    "text": text,
                    "headings": chapter.headings,
                }
            )
        except (AIServiceError, AIServiceRefused) as exc:
            chapter.status = Chapter.Status.FAILED
            chapter.save(update_fields=["status"])
            events.failed(
                document,
                f"Could not work out the topics for chapter {chapter.number}: {exc}",
                chapter_number=chapter.number,
            )
            return
        existing = save_topics(chapter, response["topics"])

    events.chapter_started(document, chapter.number, chapter.title, len(existing))

    pending = [topic for topic in existing if topic.status != Topic.Status.READY]
    total = len(existing)

    with ThreadPoolExecutor(max_workers=TOPIC_CONCURRENCY) as pool:
        results = list(pool.map(lambda topic: _write_topic(topic, text, language), pending))

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


def _write_topic(topic: Topic, text: str, language: str) -> bool:
    """One topic, in its own thread. Returns whether it succeeded.

    Each thread gets its own database connection, so it must hand it back rather than
    leave it open for the life of the task.
    """
    close_old_connections()
    try:
        topic.status = Topic.Status.GENERATING
        topic.save(update_fields=["status"])

        content = request_topic_content(
            {
                "language": language,
                "chapter_number": topic.chapter.number,
                "chapter_title": topic.chapter.title,
                "topic_title": topic.title,
                "topic_summary": topic.summary,
                "key_points": topic.key_points,
                "text": text,
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
        _fail(document, "No topic could be generated from this document.")


def _fail(document: Document, message: str) -> None:
    logger.error("document %s failed: %s", document.pk, message)
    document.status = Document.Status.FAILED
    document.error = message
    document.save(update_fields=["status", "error", "updated_at"])
    events.failed(document, message)
