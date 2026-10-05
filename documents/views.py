from django.db.models import Count, Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from curriculum.models import Chapter, Topic
from documents.models import Document, UsageRecord
from documents.serializers import DocumentSerializer, DocumentUploadSerializer
from documents.streaming import stream
from documents.tasks import process_document


def _progress_context(documents) -> dict:
    """One query for the whole list rather than two per row."""
    rows = (
        Document.objects.filter(id__in=[d.id for d in documents])
        .annotate(
            total=Count("syllabus__chapters__topics", distinct=True),
            ready=Count(
                "syllabus__chapters__topics",
                filter=Q(syllabus__chapters__topics__status=Topic.Status.READY),
                distinct=True,
            ),
            chapters=Count("syllabus__chapters", distinct=True),
            chapters_done=Count(
                "syllabus__chapters",
                filter=Q(syllabus__chapters__status=Chapter.Status.READY),
                distinct=True,
            ),
        )
        .values_list("id", "total", "ready", "chapters", "chapters_done")
    )
    # Cost is summed in Python rather than SQL because the price depends on the
    # model each call used. One query for all of them, not one per document.
    spend: dict[int, float] = {}
    calls: dict[int, int] = {}
    for record in UsageRecord.objects.filter(document__in=[d.id for d in documents]):
        spend[record.document_id] = spend.get(record.document_id, 0.0) + record.cost_usd
        calls[record.document_id] = calls.get(record.document_id, 0) + 1

    return {
        "topic_totals": {row[0]: row[1] for row in rows},
        "topic_ready": {row[0]: row[2] for row in rows},
        "chapter_totals": {row[0]: row[3] for row in rows},
        "chapter_ready": {row[0]: row[4] for row in rows},
        "spend": spend,
        "calls": calls,
    }


class DocumentListCreateView(generics.ListCreateAPIView):
    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user).select_related("syllabus")

    def get_serializer_class(self):
        return DocumentUploadSerializer if self.request.method == "POST" else DocumentSerializer

    def list(self, request: Request, *args, **kwargs) -> Response:
        documents = list(self.get_queryset())
        serializer = DocumentSerializer(
            documents, many=True, context=_progress_context(documents)
        )
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save(owner=request.user)

        # Generation runs for minutes, so the upload returns as soon as the row exists
        # and the client watches `status`.
        process_document.delay(document.id)

        body = DocumentSerializer(document, context=_progress_context([document])).data
        return Response(body, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user).select_related("syllabus")

    def get_serializer_context(self) -> dict:
        return _progress_context([self.get_object()])


class DocumentEventsView(APIView):
    """Live progress for one document, as server-sent events."""

    def get(self, request: Request, pk: int) -> StreamingHttpResponse:
        document = get_object_or_404(Document.objects.filter(owner=request.user), pk=pk)

        response = StreamingHttpResponse(
            stream(document.id, _cursor(request)), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        # Tells nginx and friends not to buffer the stream into uselessness.
        response["X-Accel-Buffering"] = "no"
        return response


def _cursor(request: Request) -> int:
    """Where to resume from. EventSource sends Last-Event-ID on its own reconnect;
    the query parameter is for a first connection that already has some history."""
    raw = request.headers.get("Last-Event-ID") or request.query_params.get("since") or "0"
    try:
        return int(raw)
    except ValueError:
        return 0
