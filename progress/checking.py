"""The Check button's comparison.

The learner is shown exactly what to type as ghost text, so an exact comparison is
fair. It is not a raw string equality though: a trailing space or a stray blank line
is invisible in the editor, and failing someone for a character they cannot see is
the one way this design goes wrong. Everything a learner *can* see — indentation,
identifiers, quote style, operators — must match.
"""

from dataclasses import dataclass


def normalise(code: str) -> str:
    lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip("\n")


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    first_mismatch_line: int | None

    @property
    def as_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "first_mismatch_line": self.first_mismatch_line}


def check(submitted: str, expected: str) -> CheckResult:
    """Compare a submission, and say which line first went wrong.

    The line number lets the editor point at the problem. It gives nothing away:
    the expected code is already on screen in grey.
    """
    submitted_lines = normalise(submitted).split("\n")
    expected_lines = normalise(expected).split("\n")

    if submitted_lines == expected_lines:
        return CheckResult(passed=True, first_mismatch_line=None)

    for index, expected_line in enumerate(expected_lines):
        if index >= len(submitted_lines) or submitted_lines[index] != expected_line:
            return CheckResult(passed=False, first_mismatch_line=index + 1)

    # Same prefix, but the submission carries extra lines past the end.
    return CheckResult(passed=False, first_mismatch_line=len(expected_lines) + 1)
