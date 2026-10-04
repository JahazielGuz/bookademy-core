"""Which language a document's exercises should be written in.

Counted from the code the book actually contains rather than asked of a model: the
fenced blocks are already extracted, and a keyword tally over them is free, instant
and good enough to tell a Python book from a JavaScript one.
"""

import re

PYTHON_MARKERS = re.compile(r"\b(def |import |print\(|elif |self\.|None\b|True\b)")
JAVASCRIPT_MARKERS = re.compile(r"(\bconst \b|\blet \b|=>|\bfunction \b|console\.log|;\s*$)")

FENCE = re.compile(r"```(.*?)```", re.DOTALL)


def detect_language(pages: list[str]) -> str:
    """Returns 'python' or 'javascript', defaulting to python on a tie."""
    code = "\n".join(block for page in pages for block in FENCE.findall(page))
    if not code:
        code = "\n".join(pages)

    python = len(PYTHON_MARKERS.findall(code))
    javascript = len(JAVASCRIPT_MARKERS.findall(code))
    return "javascript" if javascript > python else "python"
