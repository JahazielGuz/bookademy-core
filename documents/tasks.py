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
from documents.locks import document_run, keep_held
from documents.models import Document

logger = logging.getLogger(__name__)

TOPIC_CONCURRENCY = 3


class NoOutline(Exception):
    """The PDF carries no usable bookmarks, so its structure cannot be read."""


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_document(self, document_id: int) -> None:
    """Generate one book, once.

    The lock is the whole point of the wrapper: Celery redelivers a task it thinks
    was lost, and a run longer than the broker's visibility timeout looks exactly
    like a lost one. A redelivered copy finds the document already held and returns
    without spending anything.
    """
    with document_run(document_id) as token:
        if token is None:
            return
        _generate(self, document_id, token)


def _generate(task, document_id: int, token: str) -> None:
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
        if task.request.retries >= task.max_retries:
            _fail(document, str(exc))
            return
        raise task.retry(exc=exc) from exc

    # One chapter at a time, in order. Topics run concurrently inside a chapter and
    # nowhere else: chapter two must not start while chapter one is unfinished, or
    # the syllabus stops filling in from the top and the ordering guarantee is lost.
    chapters = list(syllabus.chapters.all())
    for chapter in chapters:
        _write_chapter(document, chapter)
        # Push the expiry back now rather than on a timer: a chapter is the longest
        # this run goes without a natural checkpoint.
        if not keep_held(document.pk, token):
            logger.error(
                "lost the run lock for document %s part way through; stopping rather "
                "than racing whoever holds it now",
                document.pk,
            )
            return

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
            "This PDF has no table of contents, so its chapters cannot be read. "
            "Look for a chapter list in your PDF reader's sidebar — if there isn't "
            "one, the file is most likely a scan. A publisher's original PDF of the "
            "same book will usually work."
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


# A page either side of a topic, so a sentence or a code listing that straddles the
# boundary is not cut in half.
TOPIC_MARGIN_PAGES = 1


def _slice(document: Document, first_page: int, last_page: int) -> str:
    pages = document.pages or []
    start = max(0, first_page - 1)
    end = min(len(pages), last_page)
    return "\n\n".join(pages[start:end])


def chapter_text(document: Document, chapter: Chapter) -> str:
    """The chapter's own pages. Sent once per chapter, to work out its topics."""
    return _slice(document, chapter.page_start, chapter.page_end)


def topic_text(document: Document, topic: Topic) -> str:
    """The topic's own pages, not its chapter's.

    This is the difference between a book that costs a few dollars and one that costs
    twenty. A topic covers four or five pages; sending the whole forty-page chapter
    with it — once per topic, eleven times over — multiplied the input by roughly
    seven and a half for nothing. The page range has been on the topic since it was
    created; it just was not being used.

    A page of margin either side keeps a listing that straddles the boundary intact.
    """
    return _slice(
        document,
        topic.page_start - TOPIC_MARGIN_PAGES,
        topic.page_end + TOPIC_MARGIN_PAGES,
    )


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
        results = list(
            pool.map(lambda topic: _write_topic(document, topic, language), pending)
        )

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


def _write_topic(document: Document, topic: Topic, language: str) -> bool:
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
                "text": topic_text(document, topic),
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
