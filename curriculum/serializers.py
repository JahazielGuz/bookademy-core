from rest_framework import serializers

from curriculum.models import (
    Chapter,
    Exercise,
    ExerciseStep,
    Lesson,
    Question,
    Quiz,
    Syllabus,
    Topic,
)


class StepSerializer(serializers.ModelSerializer):
    completed = serializers.SerializerMethodField()
    unlocked = serializers.SerializerMethodField()

    class Meta:
        model = ExerciseStep
        # expected_code is deliberately sent to the browser: the ghost text the
        # learner types over is rendered from it. The check still runs on the server,
        # which is what actually decides whether a step is passed.
        fields = [
            "id",
            "number",
            "instruction_markdown",
            "explanation_markdown",
            "starter_code",
            "expected_code",
            "hint",
            "completed",
            "unlocked",
        ]

    def get_completed(self, step: ExerciseStep) -> bool:
        return step.id in self.context["completed_step_ids"]

    def get_unlocked(self, step: ExerciseStep) -> bool:
        """Steps open one at a time; the first one is always open."""
        if step.number == 1:
            return True
        previous = self.context["steps_by_exercise"][step.exercise_id].get(step.number - 1)
        return previous is not None and previous in self.context["completed_step_ids"]


class ExerciseSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True, read_only=True)

    class Meta:
        model = Exercise
        fields = ["id", "position", "title", "scenario_markdown", "language", "steps"]


class QuestionSerializer(serializers.ModelSerializer):
    """correct_index and explanation are withheld until an attempt is submitted."""

    class Meta:
        model = Question
        fields = ["id", "position", "prompt", "choices"]


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    best_score = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = ["id", "questions", "best_score"]

    def get_best_score(self, quiz: Quiz) -> int | None:
        return self.context["best_quiz_scores"].get(quiz.id)


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ["id", "title", "body_markdown"]


class TopicDetailSerializer(serializers.ModelSerializer):
    lesson = LessonSerializer(read_only=True)
    quiz = QuizSerializer(read_only=True)
    exercises = ExerciseSerializer(many=True, read_only=True)
    chapter_number = serializers.IntegerField(source="chapter.number", read_only=True)
    chapter_title = serializers.CharField(source="chapter.title", read_only=True)
    document_id = serializers.IntegerField(source="chapter.syllabus.document_id", read_only=True)

    class Meta:
        model = Topic
        fields = [
            "id",
            "position",
            "title",
            "summary",
            "key_points",
            "status",
            "error",
            "chapter_number",
            "chapter_title",
            "document_id",
            "lesson",
            "quiz",
            "exercises",
        ]


class TopicSummarySerializer(serializers.ModelSerializer):
    """The syllabus row: enough to render a tick and a progress count."""

    steps_total = serializers.SerializerMethodField()
    steps_completed = serializers.SerializerMethodField()
    quiz_passed = serializers.SerializerMethodField()
    complete = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = [
            "id",
            "position",
            "title",
            "summary",
            "status",
            "steps_total",
            "steps_completed",
            "quiz_passed",
            "complete",
        ]

    def get_steps_total(self, topic: Topic) -> int:
        return self.context["step_totals"].get(topic.id, 0)

    def get_steps_completed(self, topic: Topic) -> int:
        return self.context["step_completions"].get(topic.id, 0)

    def get_quiz_passed(self, topic: Topic) -> bool:
        return topic.id in self.context["passed_quiz_topic_ids"]

    def get_complete(self, topic: Topic) -> bool:
        """Derived, never stored: every step passed and the quiz passed."""
        total = self.get_steps_total(topic)
        return (
            total > 0
            and self.get_steps_completed(topic) == total
            and self.get_quiz_passed(topic)
        )


class ChapterSerializer(serializers.ModelSerializer):
    topics = TopicSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id",
            "number",
            "title",
            "summary",
            "page_start",
            "page_end",
            "status",
            "topics",
        ]


class SyllabusSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(many=True, read_only=True)

    class Meta:
        model = Syllabus
        fields = ["id", "title", "subject", "description", "language", "chapters"]
