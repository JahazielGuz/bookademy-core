"""Seed one hand-written course.

Lets the whole interface be exercised — syllabus, ticks, ghost text, Check, Next,
quiz — without running a generation pass or spending anything on the API.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

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
from documents.models import Document

User = get_user_model()

EMAIL = "demo@bookademy.test"
PASSWORD = "practice-makes-perfect"

LESSON_BODY = """\
Whenever a function is called, a new **local scope** is created. Names created inside
that scope are not visible to code outside it.

```python
def favorite_color():
    color = 'Red'

print(color)
```

`color` is scoped locally to `favorite_color()`. The `print(color)` on the last line
runs in the outer scope, has no access to the function's local names, and raises a
`NameError`.

Move the call inside the function and the name is in scope:

```python
def favorite_color():
    color = 'Red'
    print(color)

favorite_color()
```

Now the output is `Red`.
"""

QUESTIONS = [
    (
        "When is a new local scope created?",
        ["Every time a function is called", "Once, when the module is imported"],
        0,
        "Each call gets its own local namespace, which is why recursion works at all.",
    ),
    (
        "Why does `print(color)` fail when it sits outside the function?",
        [
            "The outer scope cannot see names created in a local scope",
            "`color` was never assigned a value",
        ],
        0,
        "It was assigned — but only inside the function's local namespace.",
    ),
    (
        "Which scope is the deepest of the four?",
        ["Local", "Built-in"],
        0,
        "Local is innermost; code in outer scopes cannot reach into it.",
    ),
]

STEPS = [
    (
        "Define a function called `favorite_color`.",
        "A function gives the paint shop somewhere to keep the colour it is working "
        "with, without that name leaking into the rest of the program.",
        "",
        "def favorite_color():",
    ),
    (
        "Inside the function, assign the string `'Red'` to `color`.",
        "Assigning inside the body puts `color` in the function's local namespace. "
        "Nothing outside the function can read it.",
        "def favorite_color():",
        "def favorite_color():\n    color = 'Red'",
    ),
    (
        "Still inside the function, print `color`.",
        "The `print()` call is now in the same local scope as `color`, so the name "
        "resolves. This is the fix for the `NameError`.",
        "def favorite_color():\n    color = 'Red'",
        "def favorite_color():\n    color = 'Red'\n    print(color)",
    ),
    (
        "Below the function, call `favorite_color()`.",
        "Defining a function does not run it. The call is what creates the local "
        "scope and produces the output.",
        "def favorite_color():\n    color = 'Red'\n    print(color)",
        "def favorite_color():\n    color = 'Red'\n    print(color)\n\nfavorite_color()",
    ),
]


class Command(BaseCommand):
    help = "Create a demo learner and one hand-written course."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        user, created = User.objects.get_or_create(
            email=EMAIL, defaults={"display_name": "Demo"}
        )
        if created:
            user.set_password(PASSWORD)
            user.save()

        Document.objects.filter(owner=user, title="Learning Python").delete()
        document = Document.objects.create(
            owner=user,
            title="Learning Python",
            file="documents/demo/learning-python.pdf",
            page_count=284,
            status=Document.Status.READY,
        )
        syllabus = Syllabus.objects.create(
            document=document,
            title="Learning Python",
            subject="Python programming",
            description="Scope, namespaces and the rules that decide which name wins.",
            language="python",
        )

        chapter = Chapter.objects.create(
            syllabus=syllabus,
            number=1,
            title="Scope",
            summary="Where a name can be seen from, and why that matters.",
            page_start=180,
            page_end=206,
        )
        topic = Topic.objects.create(
            chapter=chapter,
            position=1,
            title="Local scope",
            summary="Names created inside a function belong to that call and nowhere else.",
            key_points=[
                "Each function call creates its own local scope",
                "Outer scopes cannot read names from a local scope",
                "A name used before it is in scope raises NameError",
            ],
            page_start=182,
            page_end=186,
            status=Topic.Status.READY,
        )
        Lesson.objects.create(topic=topic, title="Local scope", body_markdown=LESSON_BODY)

        quiz = Quiz.objects.create(topic=topic)
        for position, (prompt, choices, correct, explanation) in enumerate(QUESTIONS, start=1):
            Question.objects.create(
                quiz=quiz,
                position=position,
                prompt=prompt,
                choices=choices,
                correct_index=correct,
                explanation=explanation,
            )

        exercise = Exercise.objects.create(
            topic=topic,
            position=1,
            title="Keep the colour inside the function",
            scenario_markdown=(
                "Jiho is starting a painting business. The app below prints the colour "
                "needed for a job — but it raises a `NameError`. Build it back up one "
                "line at a time, with the print in the right scope."
            ),
            language="python",
        )
        for number, (instruction, explanation, starter, expected) in enumerate(STEPS, start=1):
            ExerciseStep.objects.create(
                exercise=exercise,
                number=number,
                instruction_markdown=instruction,
                explanation_markdown=explanation,
                starter_code=starter,
                expected_code=expected,
                hint="Four spaces of indentation put a line inside the function body."
                if number in (2, 3)
                else "",
            )

        # A second topic, left pending, so the "still being written" state is visible.
        Topic.objects.create(
            chapter=chapter,
            position=2,
            title="Global scope",
            summary="Names defined at module level, and what `global` actually does.",
            key_points=["Module-level names are visible to functions"],
            page_start=187,
            page_end=192,
            status=Topic.Status.GENERATING,
        )

        self.stdout.write(self.style.SUCCESS(f"Seeded {EMAIL} / {PASSWORD}"))
