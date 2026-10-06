"""The generated course. Mirrors the AI service's schemas module field for field;
changing one without the other is how the two drift apart."""

from django.db import models


class Language(models.TextChoices):
    PYTHON = "python", "Python"
    JAVASCRIPT = "javascript", "JavaScript"


class Syllabus(models.Model):
    document = models.OneToOneField(
        "documents.Document", on_delete=models.CASCADE, related_name="syllabus"
    )
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    language = models.CharField(max_length=16, choices=Language.choices)

    class Meta:
        verbose_name_plural = "syllabi"

    def __str__(self) -> str:
        return self.title


class Chapter(models.Model):
    """Chapters are written one at a time, in order, so each carries its own status
    and the syllabus can show chapter 1 finished while chapter 2 is still being
    written."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        GENERATING = "generating", "Being written"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name="chapters")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    summary = models.TextField()
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    # The book's own section headings for this chapter, kept as candidates for the
    # topics call. They are a strong prior, not a syllabus: this book carries between
    # 4 and 54 of them per chapter, so they need merging before they are lessons.
    headings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["syllabus", "number"], name="unique_chapter_number")
        ]

    def __str__(self) -> str:
        return f"{self.number}. {self.title}"


class Topic(models.Model):
    """One item of a course, and exactly one kind of thing.

    A lesson is reading plus typed exercises and needs the editor beside it. A quiz is
    questions, one at a time, and needs the whole page. Trying to be both at once put a
    quiz at the bottom of a lesson with a code editor sitting uselessly beside it, so
    they are separate items that happen to sit next to each other in a chapter.

    Content is generated per topic, so status lives here and the syllabus can render
    with some topics ready and others still being written.
    """

    class Kind(models.TextChoices):
        LESSON = "lesson", "Lesson"
        QUIZ = "quiz", "Quiz"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        GENERATING = "generating", "Being written"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="topics")
    position = models.PositiveIntegerField()
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.LESSON)
    title = models.CharField(max_length=255)
    summary = models.TextField()
    key_points = models.JSONField(default=list)
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["chapter", "position"], name="unique_topic_position")
        ]

    def __str__(self) -> str:
        return self.title


class Lesson(models.Model):
    topic = models.OneToOneField(Topic, on_delete=models.CASCADE, related_name="lesson")
    title = models.CharField(max_length=255)
    body_markdown = models.TextField()

    def __str__(self) -> str:
        return self.title


class Quiz(models.Model):
    topic = models.OneToOneField(Topic, on_delete=models.CASCADE, related_name="quiz")

    class Meta:
        verbose_name_plural = "quizzes"

    def __str__(self) -> str:
        return f"Quiz for {self.topic.title}"


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveIntegerField()
    prompt = models.TextField()

    # A list of strings. correct_index points into it and is never serialised to the
    # client, which is why the choices do not each need a row of their own.
    choices = models.JSONField(default=list)
    correct_index = models.PositiveIntegerField()
    explanation = models.TextField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "position"], name="unique_question_position")
        ]

    def __str__(self) -> str:
        return self.prompt[:60]


class Exercise(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="exercises")
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    scenario_markdown = models.TextField()
    language = models.CharField(max_length=16, choices=Language.choices)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["topic", "position"], name="unique_exercise_position")
        ]

    def __str__(self) -> str:
        return self.title


class ExerciseStep(models.Model):
    """One checkpoint. The learner types from starter_code to expected_code, with the
    remaining characters shown as ghost text."""

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="steps")
    number = models.PositiveIntegerField()
    instruction_markdown = models.TextField()
    explanation_markdown = models.TextField()
    starter_code = models.TextField(blank=True)
    expected_code = models.TextField()
    hint = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["exercise", "number"], name="unique_step_number")
        ]

    def __str__(self) -> str:
        return f"{self.exercise.title} step {self.number}"
