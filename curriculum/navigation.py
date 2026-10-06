"""What comes before and after a content item.

The syllabus is a flat sequence of items even though it is stored as a tree: a topic's
lesson, then its quiz, then the next topic's lesson, and over a chapter boundary into
the next chapter. Walking it here rather than in the browser means the client never has
to hold the whole syllabus to know where "next" goes.
"""

from dataclasses import dataclass

from curriculum.models import Topic

LESSON = "lesson"
QUIZ = "quiz"


@dataclass(frozen=True)
class Item:
    topic_id: int
    part: str


def _sequence(topic: Topic) -> list[Item]:
    """Every item in the document, in the order a learner meets them.

    Only ready topics appear: an item still being written is not somewhere Next should
    send anyone, and a failed one has nothing behind it.
    """
    topics = (
        Topic.objects.filter(
            chapter__syllabus=topic.chapter.syllabus_id, status=Topic.Status.READY
        )
        .select_related("chapter")
        .order_by("chapter__number", "position")
    )
    items: list[Item] = []
    for candidate in topics:
        items.append(Item(candidate.pk, LESSON))
        items.append(Item(candidate.pk, QUIZ))
    return items


def neighbours(topic: Topic, part: str) -> tuple[Item | None, Item | None]:
    """The item before and the item after this one, or None at either end."""
    items = _sequence(topic)
    try:
        index = items.index(Item(topic.pk, part))
    except ValueError:
        return None, None
    before = items[index - 1] if index > 0 else None
    after = items[index + 1] if index + 1 < len(items) else None
    return before, after
