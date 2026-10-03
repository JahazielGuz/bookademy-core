"""Recording what the generation run is doing.

One place that writes GenerationEvent rows, so the wording the learner sees is not
scattered through the task code.
"""

from documents.models import Document, GenerationEvent


def record(
    document: Document,
    kind: str,
    message: str,
    chapter_number: int | None = None,
) -> GenerationEvent:
    return GenerationEvent.objects.create(
        document=document, kind=kind, message=message, chapter_number=chapter_number
    )


def started(document: Document) -> None:
    record(document, GenerationEvent.Kind.STARTED, "Reading your PDF.")


def uploaded(document: Document, page_count: int) -> None:
    record(
        document,
        GenerationEvent.Kind.UPLOADED,
        f"Read {page_count} pages. Working out the syllabus — this is the slow part.",
    )


def syllabus_ready(document: Document, chapters: int, topics: int) -> None:
    record(
        document,
        GenerationEvent.Kind.SYLLABUS_READY,
        f"Syllabus ready: {chapters} chapters, {topics} topics. "
        f"Writing them in order, so chapter 1 arrives first.",
    )


def chapter_started(document: Document, number: int, title: str, topics: int) -> None:
    record(
        document,
        GenerationEvent.Kind.CHAPTER_STARTED,
        f"Writing chapter {number}: {title} ({topics} topics)",
        chapter_number=number,
    )


def topic_ready(document: Document, number: int, title: str, done: int, total: int) -> None:
    record(
        document,
        GenerationEvent.Kind.TOPIC_READY,
        f"{title} — {done} of {total} topics in this chapter",
        chapter_number=number,
    )


def chapter_ready(document: Document, number: int, title: str) -> None:
    record(
        document,
        GenerationEvent.Kind.CHAPTER_READY,
        f"Chapter {number} is ready: {title}",
        chapter_number=number,
    )


def failed(document: Document, message: str, chapter_number: int | None = None) -> None:
    record(document, GenerationEvent.Kind.FAILED, message, chapter_number=chapter_number)


def done(document: Document, chapters: int) -> None:
    record(
        document,
        GenerationEvent.Kind.DONE,
        f"All {chapters} chapters are ready.",
    )
