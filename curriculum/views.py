from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from curriculum.models import Syllabus, Topic
from curriculum.serializers import SyllabusSerializer, TopicDetailSerializer
from progress import queries


class SyllabusView(APIView):
    """The table of contents, with each topic's tick state for this learner."""

    def get(self, request: Request, document_id: int) -> Response:
        syllabus = get_object_or_404(
            Syllabus.objects.prefetch_related("chapters__topics"),
            document_id=document_id,
            document__owner=request.user,
        )
        topic_ids = [
            topic.id for chapter in syllabus.chapters.all() for topic in chapter.topics.all()
        ]
        context = {
            "step_totals": queries.step_totals(topic_ids),
            "step_completions": queries.step_completions(request.user, topic_ids),
            "passed_quiz_topic_ids": queries.passed_quiz_topic_ids(request.user, topic_ids),
        }
        return Response(SyllabusSerializer(syllabus, context=context).data)


class TopicDetailView(APIView):
    """Everything the lesson page needs in one request: the reading pane, the quiz,
    and every exercise step with its ghost-text target."""

    def get(self, request: Request, pk: int) -> Response:
        topic = get_object_or_404(
            Topic.objects.select_related(
                "chapter__syllabus__document", "lesson", "quiz"
            ).prefetch_related("exercises__steps", "quiz__questions"),
            pk=pk,
            chapter__syllabus__document__owner=request.user,
        )
        context = {
            "completed_step_ids": queries.completed_step_ids(request.user, topic),
            "steps_by_exercise": queries.steps_by_exercise(topic),
            "best_quiz_scores": queries.best_quiz_scores(request.user, topic),
        }
        return Response(TopicDetailSerializer(topic, context=context).data)
