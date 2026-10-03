from django.contrib import admin

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


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 0
    fields = ["position", "title", "status"]


@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ["title", "subject", "language", "document"]


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ["number", "title", "syllabus"]
    inlines = [TopicInline]


class StepInline(admin.TabularInline):
    model = ExerciseStep
    extra = 0
    fields = ["number", "instruction_markdown", "expected_code"]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["title", "topic", "language"]
    inlines = [StepInline]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ["title", "chapter", "position", "status"]
    list_filter = ["status"]


admin.site.register([Lesson, Quiz, Question])
