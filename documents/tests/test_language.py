from documents.language import detect_language


def test_a_python_book_is_detected():
    pages = ["```\ndef greet(name):\n    print(name)\n```", "Some prose about None and True."]

    assert detect_language(pages) == "python"


def test_a_javascript_book_is_detected():
    pages = ["```\nconst x = 1\nconsole.log(x)\n```", "An arrow function => is common."]

    assert detect_language(pages) == "javascript"


def test_only_fenced_code_is_counted_when_there_is_any():
    """Prose mentioning the other language must not outvote the actual listings."""
    pages = ["```\nconst a = 1\nlet b = 2\nconsole.log(a)\n```\nThis book replaces def and import."]

    assert detect_language(pages) == "javascript"


def test_prose_is_used_when_there_is_no_code():
    assert detect_language(["A chapter about def and import and print()"]) == "python"


def test_an_empty_document_defaults_to_python():
    assert detect_language([]) == "python"
