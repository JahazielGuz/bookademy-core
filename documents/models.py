from django.conf import settings
from django.db import models


class Document(models.Model):
    """An uploaded PDF and the state of the generation run over it."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting to start"
        UPLOADING = "uploading", "Sending to the AI service"
        OUTLINING = "outlining", "Building the syllabus"
        GENERATING = "generating", "Writing lessons and exercises"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/%Y/%m/")
    page_count = models.PositiveIntegerField(null=True, blank=True)

    # The document's text, one Markdown string per page. Extracted once, then
    # sliced per chapter — the PDF itself is never sent to a model, because that
    # would make it render every page as an image as well as reading the text.
    pages = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class GenerationEvent(models.Model):
    """An append-only log of what the generation run is doing.

    The browser reads this over SSE, using the row id as its cursor, so a reconnect
    resumes exactly where it left off instead of replaying from the start.
    """

    class Kind(models.TextChoices):
        STARTED = "started", "Started"
        UPLOADED = "uploaded", "PDF uploaded"
        SYLLABUS_READY = "syllabus_ready", "Syllabus ready"
        CHAPTER_STARTED = "chapter_started", "Chapter started"
        TOPIC_READY = "topic_ready", "Topic ready"
        CHAPTER_READY = "chapter_ready", "Chapter ready"
        FAILED = "failed", "Failed"
        DONE = "done", "Done"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.TextField()
    chapter_number = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["document", "id"])]

    def __str__(self) -> str:
        return f"{self.kind}: {self.message[:60]}"


class UsageRecord(models.Model):
    """What one generation call consumed, and what it cost.

    Recorded because the alternative is arithmetic, and arithmetic is how this
    project predicted $5 and spent $20. Every call is stored, including the ones that
    produced nothing useful, so the total is what was actually billed rather than what
    the surviving content suggests.
    """

    class Kind(models.TextChoices):
        OVERVIEW = "overview", "Summarising the book"
        TOPICS = "topics", "Working out a chapter's topics"
        CONTENT = "content", "Writing a topic"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="usage")
    chapter_number = models.PositiveIntegerField(null=True, blank=True)
    topic_title = models.CharField(max_length=255, blank=True)

    kind = models.CharField(max_length=16, choices=Kind.choices)
    model = models.CharField(max_length=64)

    input_tokens = models.PositiveIntegerField()
    cached_input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["document", "id"])]

    @property
    def cost_usd(self) -> float:
        """Priced from the table in settings.

        Cached input is billed separately and far cheaper, so it is counted
        separately — folding it into input would overstate every total.
        """
        from django.conf import settings

        prices = settings.MODEL_PRICES.get(self.model)
        if prices is None:
            return 0.0

        fresh_input = max(0, self.input_tokens - self.cached_input_tokens)
        return (
            fresh_input * prices["input"]
            + self.cached_input_tokens * prices["cached"]
            + self.output_tokens * prices["output"]
        ) / 1_000_000

    def __str__(self) -> str:
        return f"{self.kind} on {self.model}: ${self.cost_usd:.4f}"
