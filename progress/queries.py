"""Progress lookups for the curriculum serialisers.

One aggregate query per fact, built for a whole syllabus or a whole topic at a time,
because the alternative is a query per step while rendering a table of contents.
"""

from django.db.models import Count, F, Max

from curriculum.models import ExerciseStep, Topic
from progress.models import QuizAttempt, StepCompletion


def step_totals(topic_ids: list[int]) -> dict[int, int]:
    rows = (
        Topic.objects.filter(id__in=topic_ids)
        .annotate(total=Count("exercises__steps"))
        .values_list("id", "total")
    )
    return dict(rows)


def step_completions(user, topic_ids: list[int]) -> dict[int, int]:
    rows = (
        StepCompletion.objects.filter(
            user=user, step__exercise__topic_id__in=topic_ids
        )
        .values("step__exercise__topic_id")
        .annotate(done=Count("id"))
        .values_list("step__exercise__topic_id", "done")
    )
    return dict(rows)


def passed_quiz_topic_ids(user, topic_ids: list[int]) -> set[int]:
    """A quiz is passed when some attempt got every question right."""
    return set(
        QuizAttempt.objects.filter(
            user=user, quiz__topic_id__in=topic_ids, total__gt=0, score=F("total")
        ).values_list("quiz__topic_id", flat=True)
    )


def completed_step_ids(user, topic: Topic) -> set[int]:
    return set(
        StepCompletion.objects.filter(user=user, step__exercise__topic=topic).values_list(
            "step_id", flat=True
        )
    )


def steps_by_exercise(topic: Topic) -> dict[int, dict[int, int]]:
    """{exercise_id: {step number: step id}} so a step can find its predecessor
    without another query per step."""
    index: dict[int, dict[int, int]] = {}
    rows = ExerciseStep.objects.filter(exercise__topic=topic).values_list(
        "exercise_id", "number", "id"
    )
    for exercise_id, number, step_id in rows:
        index.setdefault(exercise_id, {})[number] = step_id
    return index


def best_quiz_scores(user, topic: Topic) -> dict[int, int]:
    rows = (
        QuizAttempt.objects.filter(user=user, quiz__topic=topic)
        .values("quiz_id")
        .annotate(best=Max("score"))
        .values_list("quiz_id", "best")
    )
    return dict(rows)
