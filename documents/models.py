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

    # The Anthropic Files API id. Uploaded once, then reused by every topic call.
    ai_file_id = models.CharField(max_length=128, blank=True)

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
