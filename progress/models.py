from django.conf import settings
from django.db import models


class StepCompletion(models.Model):
    """One row per learner per passed step. Everything the syllabus ticks off is
    derived from these rows, so there is no completion flag to keep in sync."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="step_completions"
    )
    step = models.ForeignKey(
        "curriculum.ExerciseStep", on_delete=models.CASCADE, related_name="completions"
    )
    submitted_code = models.TextField()
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "step"], name="unique_step_completion")
        ]

    def __str__(self) -> str:
        return f"{self.user} passed {self.step}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    quiz = models.ForeignKey("curriculum.Quiz", on_delete=models.CASCADE, related_name="attempts")

    # {question_id: chosen_index}, kept so a learner can see what they answered.
    answers = models.JSONField(default=dict)
    score = models.PositiveIntegerField()
    total = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def passed(self) -> bool:
        """A topic counts as quizzed once every question is right."""
        return self.total > 0 and self.score == self.total

    def __str__(self) -> str:
        return f"{self.user}: {self.score}/{self.total}"
