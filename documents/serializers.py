from rest_framework import serializers

from documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    syllabus_id = serializers.IntegerField(source="syllabus.id", read_only=True, default=None)
    topics_total = serializers.SerializerMethodField()
    topics_ready = serializers.SerializerMethodField()

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
        ]
        read_only_fields = ["page_count", "status", "error", "created_at"]

    def get_topics_total(self, document: Document) -> int:
        return self.context["topic_totals"].get(document.id, 0)

    def get_topics_ready(self, document: Document) -> int:
        return self.context["topic_ready"].get(document.id, 0)


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
