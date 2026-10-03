from rest_framework import serializers


class CheckSerializer(serializers.Serializer):
    code = serializers.CharField(allow_blank=True, trim_whitespace=False)


class QuizAttemptSerializer(serializers.Serializer):
    """{question_id: chosen_index}, as strings because JSON object keys are strings."""

    answers = serializers.DictField(child=serializers.IntegerField())
