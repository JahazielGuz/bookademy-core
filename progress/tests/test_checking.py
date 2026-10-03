"""The Check button's comparison.

The rule being pinned down: things a learner can see must match, things they cannot
see must not matter.
"""

from progress.checking import check, normalise


def test_identical_code_passes():
    assert check("x = 1", "x = 1").passed


def test_trailing_whitespace_is_invisible_so_it_is_forgiven():
    assert check("x = 1   ", "x = 1").passed


def test_trailing_blank_lines_are_forgiven():
    assert check("x = 1\n\n\n", "x = 1").passed


def test_windows_line_endings_are_forgiven():
    assert check("a = 1\r\nb = 2", "a = 1\nb = 2").passed


def test_indentation_must_match():
    assert not check("def f():\n  return 1", "def f():\n    return 1").passed


def test_quote_style_must_match():
    assert not check('name = "Red"', "name = 'Red'").passed


def test_identifier_names_must_match():
    assert not check("total = 0", "count = 0").passed


def test_missing_line_reports_the_line_it_wanted():
    result = check("a = 1", "a = 1\nb = 2")
    assert not result.passed
    assert result.first_mismatch_line == 2


def test_wrong_line_reports_that_line():
    result = check("a = 1\nb = 3", "a = 1\nb = 2")
    assert result.first_mismatch_line == 2


def test_extra_trailing_code_is_reported_past_the_end():
    result = check("a = 1\nb = 2\nc = 3", "a = 1\nb = 2")
    assert not result.passed
    assert result.first_mismatch_line == 3


def test_empty_submission_against_empty_expectation_passes():
    assert check("", "").passed


def test_normalise_keeps_interior_blank_lines():
    assert normalise("a\n\nb") == "a\n\nb"
