from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from curriculum.models import ExerciseStep, Quiz
from progress.checking import check
from progress.models import QuizAttempt, StepCompletion
from progress.serializers import CheckSerializer, QuizAttemptSerializer


class StepCheckView(APIView):
    """The Check button. The server decides, so Next cannot be reached by editing
    the page."""

    def post(self, request: Request, pk: int) -> Response:
        payload = CheckSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        step = get_object_or_404(
            ExerciseStep.objects.select_related("exercise"),
            pk=pk,
            exercise__topic__chapter__syllabus__document__owner=request.user,
        )

        if not self._unlocked(request.user, step):
            return Response(
                {"detail": "Finish the previous step first."}, status=status.HTTP_409_CONFLICT
            )

        result = check(payload.validated_data["code"], step.expected_code)

        if result.passed:
            StepCompletion.objects.update_or_create(
                user=request.user,
                step=step,
                defaults={"submitted_code": payload.validated_data["code"]},
            )

        next_step = (
            ExerciseStep.objects.filter(exercise=step.exercise, number=step.number + 1)
            .values_list("id", flat=True)
            .first()
        )
        return Response({**result.as_dict, "next_step_id": next_step if result.passed else None})

    def _unlocked(self, user, step: ExerciseStep) -> bool:
        if step.number == 1:
            return True
        previous = ExerciseStep.objects.filter(
            exercise=step.exercise, number=step.number - 1
        ).first()
        return previous is not None and StepCompletion.objects.filter(
            user=user, step=previous
        ).exists()


class QuizAttemptView(APIView):
    """Grade a whole quiz at once, and only then reveal the answers."""

    def post(self, request: Request, pk: int) -> Response:
        payload = QuizAttemptSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        quiz = get_object_or_404(
            Quiz.objects.prefetch_related("questions"),
            pk=pk,
            topic__chapter__syllabus__document__owner=request.user,
        )

        answers = payload.validated_data["answers"]
        questions = list(quiz.questions.all())
        missing = [q.id for q in questions if str(q.id) not in answers]
        if missing:
            return Response(
                {"detail": "Answer every question before submitting.", "missing": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        score = 0
        for question in questions:
            chosen = answers[str(question.id)]
            correct = chosen == question.correct_index
            score += correct
            results.append(
                {
                    "question_id": question.id,
                    "chosen_index": chosen,
                    "correct_index": question.correct_index,
                    "correct": correct,
                    "explanation": question.explanation,
                }
            )

        attempt = QuizAttempt.objects.create(
            user=request.user,
            quiz=quiz,
            answers=answers,
            score=score,
            total=len(questions),
        )
        return Response(
            {
                "score": attempt.score,
                "total": attempt.total,
                "passed": attempt.passed,
                "results": results,
            },
            status=status.HTTP_201_CREATED,
        )
