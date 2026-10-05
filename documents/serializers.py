from rest_framework import serializers

from documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    syllabus_id = serializers.IntegerField(source="syllabus.id", read_only=True, default=None)
    topics_total = serializers.SerializerMethodField()
    topics_ready = serializers.SerializerMethodField()
    # Chapters are known as soon as the document is read, so unlike the topic count
    # this is a total that does not move while the run is going.
    chapters_total = serializers.SerializerMethodField()
    chapters_ready = serializers.SerializerMethodField()
    # What this document has actually cost, from recorded usage rather than an
    # estimate.
    cost_usd = serializers.SerializerMethodField()
    calls_made = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "page_count",
            "status",
            "error",
            "created_at",
            "syllabus_id",
            "topics_total",
            "topics_ready",
            "chapters_total",
            "chapters_ready",
            "cost_usd",
            "calls_made",
        ]
        read_only_fields = ["page_count", "status", "error", "created_at"]

    def get_topics_total(self, document: Document) -> int:
        return self.context["topic_totals"].get(document.id, 0)

    def get_topics_ready(self, document: Document) -> int:
        return self.context["topic_ready"].get(document.id, 0)

    def get_chapters_total(self, document: Document) -> int:
        return self.context["chapter_totals"].get(document.id, 0)

    def get_chapters_ready(self, document: Document) -> int:
        return self.context["chapter_ready"].get(document.id, 0)

    def get_cost_usd(self, document: Document) -> float:
        return round(self.context["spend"].get(document.id, 0.0), 4)

    def get_calls_made(self, document: Document) -> int:
        return self.context["calls"].get(document.id, 0)


class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "file"]
        extra_kwargs = {"title": {"required": False}}

    def validate_file(self, value):
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files can be uploaded.")
        return value

    def create(self, validated_data: dict) -> Document:
        # The real title arrives with the syllabus; the filename holds the place so
        # the library is not full of blank rows while generation runs.
        if not validated_data.get("title"):
            validated_data["title"] = validated_data["file"].name.rsplit(".", 1)[0]
        return super().create(validated_data)
